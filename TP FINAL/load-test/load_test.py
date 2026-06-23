"""
Teste de concorrência/carga – Sistema de Chat Distribuído
Simula N usuários fazendo login e trocando mensagens simultaneamente.

Uso:
  pip install httpx websockets
  python load_test.py --users 10 --messages 5 --host localhost

O script:
  1. Registra N usuários (se não existirem).
  2. Todos fazem login em paralelo.
  3. Todos conectam via WebSocket.
  4. Cada usuário envia M mensagens para o canal geral.
  5. Coleta métricas: latência de login, mensagens enviadas/recebidas, erros.
"""
import asyncio
import time
import argparse
import json
import statistics
from dataclasses import dataclass, field
from typing import List

import httpx
import websockets


@dataclass
class UserResult:
    user_id: int
    username: str
    login_time_ms: float = 0.0
    messages_sent: int = 0
    messages_received: int = 0
    errors: List[str] = field(default_factory=list)


async def register_and_login(client: httpx.AsyncClient, username: str, password: str, base_url: str) -> dict:
    # Tenta registrar (ignora se já existe)
    await client.post(f"{base_url}/api/auth/register", json={"username": username, "password": password})

    t0 = time.perf_counter()
    res = await client.post(
        f"{base_url}/api/auth/login",
        data={"username": username, "password": password},
    )
    login_ms = (time.perf_counter() - t0) * 1000
    res.raise_for_status()
    data = res.json()
    data["login_time_ms"] = login_ms
    return data


async def run_user(
    username: str,
    password: str,
    base_url: str,
    ws_base: str,
    num_messages: int,
    result: UserResult,
    ready_event: asyncio.Event,
    start_event: asyncio.Event,
):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            auth = await register_and_login(client, username, password, base_url)

        result.user_id = auth["user_id"]
        result.login_time_ms = auth["login_time_ms"]
        token = auth["access_token"]
        user_id = auth["user_id"]

        ws_url = f"{ws_base}/ws/{user_id}?token={token}"

        async with websockets.connect(ws_url, open_timeout=10) as ws:
            # Consome welcome
            await asyncio.wait_for(ws.recv(), timeout=5)

            ready_event.set()
            await start_event.wait()  # Espera todos estarem prontos

            send_tasks = []
            recv_count = 0

            async def sender():
                for i in range(num_messages):
                    payload = json.dumps({
                        "content": f"[{username}] mensagem {i+1}",
                        "room_id": "geral",
                    })
                    await ws.send(payload)
                    result.messages_sent += 1
                    await asyncio.sleep(0.05)

            async def receiver():
                nonlocal recv_count
                deadline = time.time() + num_messages * 0.5 + 3
                while time.time() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1)
                        msg = json.loads(raw)
                        if msg.get("type") == "message":
                            recv_count += 1
                            result.messages_received += 1
                    except asyncio.TimeoutError:
                        break

            await asyncio.gather(sender(), receiver())

    except Exception as e:
        result.errors.append(str(e))


async def run_load_test(num_users: int, num_messages: int, host: str, port_http: int = 80):
    base_url = f"http://{host}:{port_http}"
    ws_base = f"ws://{host}:{port_http}"

    print(f"\n{'='*55}")
    print(f" Teste de Carga – Chat Distribuído")
    print(f" Usuários: {num_users}  |  Mensagens/usuário: {num_messages}")
    print(f" Alvo: {base_url}")
    print(f"{'='*55}\n")

    results = [UserResult(user_id=0, username=f"loaduser{i:03d}") for i in range(num_users)]
    ready_events = [asyncio.Event() for _ in range(num_users)]
    start_event = asyncio.Event()

    async def wait_all_ready():
        await asyncio.gather(*[e.wait() for e in ready_events])
        print(f"[*] Todos os {num_users} usuários conectados — iniciando envio simultâneo!")
        start_event.set()

    tasks = [
        run_user(
            username=f"loaduser{i:03d}",
            password="senha123",
            base_url=base_url,
            ws_base=ws_base,
            num_messages=num_messages,
            result=results[i],
            ready_event=ready_events[i],
            start_event=start_event,
        )
        for i in range(num_users)
    ]

    t_start = time.perf_counter()
    await asyncio.gather(wait_all_ready(), *tasks)
    elapsed = time.perf_counter() - t_start

    # ── Métricas ──
    login_times = [r.login_time_ms for r in results if r.login_time_ms > 0]
    total_sent = sum(r.messages_sent for r in results)
    total_recv = sum(r.messages_received for r in results)
    total_errors = sum(len(r.errors) for r in results)

    print(f"\n{'='*55}")
    print(f" RESULTADOS")
    print(f"{'='*55}")
    print(f" Tempo total:              {elapsed:.2f}s")
    print(f" Usuários com sucesso:     {sum(1 for r in results if not r.errors)}/{num_users}")
    print(f" Mensagens enviadas:       {total_sent}")
    print(f" Mensagens recebidas:      {total_recv}")
    print(f" Erros:                    {total_errors}")
    if login_times:
        print(f" Login – média:            {statistics.mean(login_times):.1f}ms")
        print(f" Login – p95:              {sorted(login_times)[int(len(login_times)*0.95)]:.1f}ms")
        print(f" Login – máx:              {max(login_times):.1f}ms")
    if elapsed > 0:
        print(f" Throughput:               {total_sent/elapsed:.1f} msg/s")
    print(f"{'='*55}\n")

    if total_errors:
        print("Detalhes dos erros:")
        for r in results:
            if r.errors:
                print(f"  {r.username}: {r.errors}")

    success = total_errors == 0 and total_sent == num_users * num_messages
    print("RESULTADO FINAL:", "✓ PASSOU" if success else "✗ FALHOU")
    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Teste de carga do Chat Distribuído")
    parser.add_argument("--users", type=int, default=10, help="Número de usuários simultâneos")
    parser.add_argument("--messages", type=int, default=5, help="Mensagens por usuário")
    parser.add_argument("--host", type=str, default="localhost", help="Host do servidor")
    parser.add_argument("--port", type=int, default=80, help="Porta HTTP")
    args = parser.parse_args()

    asyncio.run(run_load_test(args.users, args.messages, args.host, args.port))
