import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    database_url: str = "postgresql://chat:chatpass@localhost:5432/chatdb"
    redis_url: str = "redis://localhost:6379"
    auth_service_url: str = "http://localhost:8001"
    jwt_secret: str = "super-secret-jwt-key-change-in-prod"
    jwt_algorithm: str = "HS256"

    class Config:
        env_file = ".env"


settings = Settings()

_db_url = settings.database_url
_connect_args = {"check_same_thread": False} if _db_url.startswith("sqlite") else {}
engine = create_engine(_db_url, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    created_by_id = Column(Integer, nullable=False)
    created_by_username = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, nullable=False, index=True)
    sender_username = Column(String(50), nullable=False)
    recipient_id = Column(Integer, nullable=True, index=True)
    room_id = Column(String(100), nullable=True, index=True)
    content = Column(Text, nullable=False)
    is_private = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


class RoomCreate(BaseModel):
    name: str


class RoomResponse(BaseModel):
    id: int
    name: str
    created_by_username: str
    created_at: datetime

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    content: str
    recipient_id: Optional[int] = None
    room_id: Optional[str] = None


class MessageResponse(BaseModel):
    id: int
    sender_id: int
    sender_username: str
    recipient_id: Optional[int]
    room_id: Optional[str]
    content: str
    is_private: bool
    created_at: datetime

    class Config:
        from_attributes = True


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")


class ConnectionManager:
    """Gerencia conexões WebSocket locais e pub/sub via Redis para escalabilidade horizontal."""

    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}
        self.redis: Optional[aioredis.Redis] = None
        self.pubsub_task: Optional[asyncio.Task] = None

    async def startup(self):
        self.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        self.pubsub_task = asyncio.create_task(self._listen_pubsub())
        logger.info("ConnectionManager iniciado com Redis pub/sub")

    async def shutdown(self):
        if self.pubsub_task:
            self.pubsub_task.cancel()
        if self.redis:
            await self.redis.aclose()

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"Usuário {user_id} conectado. Total conexões locais: {sum(len(v) for v in self.active_connections.values())}")

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket) if hasattr(self.active_connections[user_id], 'discard') else None
            try:
                self.active_connections[user_id].remove(websocket)
            except ValueError:
                pass
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"Usuário {user_id} desconectado")

    async def send_to_user(self, user_id: int, message: dict):
        """Publica via Redis (que entrega localmente via pubsub). Sem Redis, entrega direta."""
        if self.redis:
            await self.redis.publish(f"user:{user_id}", json.dumps(message))
        else:
            await self._deliver_locally(user_id, message)

    async def broadcast(self, message: dict, exclude_user: Optional[int] = None):
        """Broadcast via Redis (evita entrega dupla). Sem Redis, entrega direta."""
        if self.redis:
            payload = {"broadcast": True, "exclude_user": exclude_user, "message": message}
            await self.redis.publish("broadcast", json.dumps(payload))
        else:
            for uid, conns in list(self.active_connections.items()):
                if uid == exclude_user:
                    continue
                for ws in conns:
                    try:
                        await ws.send_json(message)
                    except Exception:
                        pass

    async def _deliver_locally(self, user_id: int, message: dict):
        if user_id in self.active_connections:
            dead = []
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                try:
                    self.active_connections[user_id].remove(ws)
                except ValueError:
                    pass

    async def _listen_pubsub(self):
        """Escuta mensagens Redis pub/sub de outras instâncias do serviço."""
        try:
            pubsub = self.redis.pubsub()
            await pubsub.psubscribe("user:*", "broadcast")
            async for raw in pubsub.listen():
                if raw["type"] not in ("message", "pmessage"):
                    continue
                channel = raw.get("channel", "")
                data = json.loads(raw["data"])

                if channel == "broadcast":
                    exclude = data.get("exclude_user")
                    msg = data.get("message", data)
                    for uid, conns in list(self.active_connections.items()):
                        if uid == exclude:
                            continue
                        for ws in conns:
                            try:
                                await ws.send_json(msg)
                            except Exception:
                                pass
                elif channel.startswith("user:"):
                    uid = int(channel.split(":")[1])
                    await self._deliver_locally(uid, data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Erro no pub/sub listener: {e}")


manager = ConnectionManager()

app = FastAPI(title="Chat Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await manager.startup()
    db = SessionLocal()
    try:
        for name in ("geral", "tecnologia", "off-topic"):
            if not db.query(Room).filter(Room.name == name).first():
                db.add(Room(name=name, created_by_id=0, created_by_username="sistema"))
        db.commit()
    finally:
        db.close()


@app.on_event("shutdown")
async def on_shutdown():
    await manager.shutdown()


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, token: str = Query(...)):
    payload = decode_token(token)
    if payload.get("user_id") != user_id:
        await websocket.close(code=4001)
        return

    username = payload.get("sub", f"user_{user_id}")
    await manager.connect(websocket, user_id)

    await manager.send_to_user(user_id, {
        "type": "system",
        "content": f"Bem-vindo, {username}!",
        "timestamp": datetime.utcnow().isoformat(),
    })

    db = SessionLocal()
    try:
        while True:
            data = await websocket.receive_json()
            content = data.get("content", "").strip()
            recipient_id = data.get("recipient_id")
            room_id = data.get("room_id")

            if not content:
                continue

            msg = Message(
                sender_id=user_id,
                sender_username=username,
                recipient_id=recipient_id,
                room_id=room_id,
                content=content,
                is_private=recipient_id is not None,
            )
            db.add(msg)
            db.commit()
            db.refresh(msg)

            payload_out = {
                "type": "message",
                "id": msg.id,
                "sender_id": user_id,
                "sender_username": username,
                "content": content,
                "recipient_id": recipient_id,
                "room_id": room_id,
                "is_private": msg.is_private,
                "timestamp": msg.created_at.isoformat(),
            }

            if recipient_id:
                # Mensagem privada 1:1
                await manager.send_to_user(user_id, payload_out)
                if recipient_id != user_id:
                    await manager.send_to_user(recipient_id, payload_out)
            else:
                # Broadcast geral (1:N)
                await manager.broadcast(payload_out)

    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"Erro WebSocket usuário {user_id}: {e}")
        manager.disconnect(websocket, user_id)
    finally:
        db.close()


@app.get("/messages", response_model=list[MessageResponse])
def get_messages(
    room_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    payload = decode_token(token)
    user_id = payload.get("user_id")

    query = db.query(Message)
    if room_id:
        query = query.filter(Message.room_id == room_id)
    else:
        # Retorna mensagens públicas + privadas do usuário
        from sqlalchemy import or_, and_
        query = query.filter(
            or_(
                Message.is_private == False,
                and_(Message.is_private == True, Message.sender_id == user_id),
                and_(Message.is_private == True, Message.recipient_id == user_id),
            )
        )

    return query.order_by(Message.created_at.desc()).offset(offset).limit(limit).all()


@app.get("/messages/private/{other_user_id}", response_model=list[MessageResponse])
def get_private_messages(
    other_user_id: int,
    limit: int = 50,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    payload = decode_token(token)
    user_id = payload.get("user_id")

    from sqlalchemy import or_, and_
    messages = (
        db.query(Message)
        .filter(
            or_(
                and_(Message.sender_id == user_id, Message.recipient_id == other_user_id),
                and_(Message.sender_id == other_user_id, Message.recipient_id == user_id),
            )
        )
        .order_by(Message.created_at.asc())
        .limit(limit)
        .all()
    )
    return messages


@app.get("/rooms", response_model=list[RoomResponse])
def list_rooms(token: str = Query(...), db: Session = Depends(get_db)):
    decode_token(token)
    return db.query(Room).order_by(Room.created_at.asc()).all()


@app.post("/rooms", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
def create_room(data: RoomCreate, token: str = Query(...), db: Session = Depends(get_db)):
    payload = decode_token(token)
    name = data.name.strip().lower().replace(" ", "-")
    if not name:
        raise HTTPException(status_code=400, detail="Nome inválido")
    existing = db.query(Room).filter(Room.name == name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Sala já existe")
    room = Room(
        name=name,
        created_by_id=payload.get("user_id"),
        created_by_username=payload.get("sub"),
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    logger.info(f"Sala criada: #{name} por {payload.get('sub')}")
    return room


@app.get("/health")
def health():
    return {"status": "ok", "service": "chat"}
