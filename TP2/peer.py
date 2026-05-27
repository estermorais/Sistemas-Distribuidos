#!/usr/bin/env python3
"""
Transferencia de Arquivos Peer-to-Peer - TP2
Uso (seeder):  python3 peer.py --port 5000 --file arquivo.bin --meta arquivo.meta.json
Uso (leecher): python3 peer.py --port 5001 --meta arquivo.meta.json --neighbors 127.0.0.1:5000
"""

import socket
import select
import struct
import json
import hashlib
import os
import sys
import time
import argparse
import threading

# --- Protocolo ---
# Header: type(4) + block_id(4) + length(4) = 12 bytes
MSG_REQUEST = 1  # cliente solicita bloco: header apenas
MSG_DATA    = 2  # servidor envia bloco:   header + dados
MSG_NOHAVE  = 3  # servidor nao tem bloco: header apenas
HEADER_FMT  = '!III'
HEADER_SIZE = struct.calcsize(HEADER_FMT)  # 12 bytes


# ---------------------------------------------------------------
# Utilitarios
# ---------------------------------------------------------------

def recv_exact(sock, n):
    """Recebe exatamente n bytes de um socket bloqueante."""
    buf = b''
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("conexao encerrada pelo par")
        buf += chunk
    return buf


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------
# Metadados
# ---------------------------------------------------------------

def create_metadata(filepath, block_size, meta_path):
    """Cria o arquivo .json de metadados a partir do arquivo original."""
    file_size    = os.path.getsize(filepath)
    total_blocks = (file_size + block_size - 1) // block_size
    checksum     = sha256_of_file(filepath)

    meta = {
        'filename':     os.path.basename(filepath),
        'file_size':    file_size,
        'block_size':   block_size,
        'total_blocks': total_blocks,
        'sha256':       checksum,
    }
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"[META] {meta_path}: {total_blocks} blocos x {block_size} B  sha256={checksum[:16]}...")
    return meta


def load_blocks(filepath, meta):
    """Carrega todos os blocos do arquivo em um dicionario {id: bytes}."""
    blocks = {}
    block_size = meta['block_size']
    with open(filepath, 'rb') as f:
        for i in range(meta['total_blocks']):
            data = f.read(block_size)
            if data:
                blocks[i] = data
    return blocks


# ---------------------------------------------------------------
# Servidor nao-bloqueante com select()
# ---------------------------------------------------------------

def _close_conn(s, inputs, recv_bufs, send_bufs):
    """Fecha e remove uma conexao de cliente do loop do servidor."""
    if s in inputs:
        inputs.remove(s)
    recv_bufs.pop(s, None)
    send_bufs.pop(s, None)
    try:
        s.close()
    except Exception:
        pass


def run_server(port, blocks, block_registry, lock):
    """
    Servidor nao-bloqueante baseado em select().

    Utiliza um unico loop de eventos para aceitar multiplas conexoes
    e responder requisicoes de blocos sem criar uma thread por cliente.
    Todos os sockets operam em modo nao-bloqueante (setblocking(False));
    select() indica quais estao prontos para leitura ou escrita, evitando
    qualquer bloqueio na espera de dados.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.setblocking(False)          # socket nao-bloqueante
    srv.bind(('0.0.0.0', port))
    srv.listen(50)
    print(f"[SERVER] ouvindo na porta {port} (select/non-blocking)")

    inputs    = [srv]   # sockets monitorados para leitura
    recv_bufs = {}      # socket -> bytes acumulados (dados recebidos)
    send_bufs = {}      # socket -> bytes pendentes  (respostas a enviar)

    while True:
        # Sockets com dados a enviar entram na lista de escrita
        outputs = [s for s in send_bufs if send_bufs.get(s)]
        try:
            readable, writable, exceptional = select.select(
                inputs, outputs, inputs, 1.0
            )
        except Exception:
            break

        # ---- Leitura ----
        for s in readable:
            if s is srv:
                # Nova conexao de cliente
                try:
                    conn, addr = s.accept()
                    conn.setblocking(False)
                    inputs.append(conn)
                    recv_bufs[conn] = b''
                    send_bufs[conn] = b''
                    print(f"[SERVER] nova conexao: {addr[0]}:{addr[1]}")
                except Exception:
                    pass
            else:
                try:
                    data = s.recv(65536)
                    if not data:
                        _close_conn(s, inputs, recv_bufs, send_bufs)
                        continue
                    recv_bufs[s] += data
                    # Processa todas as mensagens completas no buffer
                    while len(recv_bufs[s]) >= HEADER_SIZE:
                        msg_type, block_id, length = struct.unpack(
                            HEADER_FMT, recv_bufs[s][:HEADER_SIZE]
                        )
                        if len(recv_bufs[s]) < HEADER_SIZE + length:
                            break   # mensagem incompleta, aguarda mais dados
                        recv_bufs[s] = recv_bufs[s][HEADER_SIZE + length:]

                        if msg_type != MSG_REQUEST:
                            continue

                        with lock:
                            has = block_registry.get(block_id, False)
                            blk = blocks.get(block_id)

                        if has and blk is not None:
                            resp = (struct.pack(HEADER_FMT, MSG_DATA, block_id, len(blk))
                                    + blk)
                            print(f"[SERVER] bloco {block_id} -> "
                                  f"{s.getpeername()[0]}:{s.getpeername()[1]}")
                        else:
                            resp = struct.pack(HEADER_FMT, MSG_NOHAVE, block_id, 0)

                        send_bufs[s] += resp   # enfileira para envio nao-bloqueante

                except BlockingIOError:
                    pass
                except Exception:
                    _close_conn(s, inputs, recv_bufs, send_bufs)

        # ---- Escrita ----
        for s in writable:
            if s not in send_bufs or not send_bufs[s]:
                continue
            try:
                sent = s.send(send_bufs[s])   # envia o que o SO aceitar (nao-bloqueante)
                send_bufs[s] = send_bufs[s][sent:]
            except BlockingIOError:
                pass
            except Exception:
                _close_conn(s, inputs, recv_bufs, send_bufs)

        # ---- Excecoes ----
        for s in exceptional:
            _close_conn(s, inputs, recv_bufs, send_bufs)


# ---------------------------------------------------------------
# Cliente com conexoes persistentes
# ---------------------------------------------------------------

def connect_to_neighbors(neighbors, retries=5, delay=0.5):
    """
    Conecta a todos os vizinhos configurados no inicio e mantem
    as conexoes TCP abertas (persistentes) durante toda a transferencia.
    Retorna lista de (host, port, sock).
    """
    connections = []
    for host, port in neighbors:
        sock = None
        for attempt in range(retries):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(10)
                s.connect((host, port))
                sock = s
                print(f"[CLIENT] conectado a {host}:{port}")
                break
            except Exception as e:
                print(f"[CLIENT] tentativa {attempt+1}/{retries} falhou "
                      f"({host}:{port}): {e}")
                time.sleep(delay)
        if sock:
            connections.append((host, port, sock))
        else:
            print(f"[CLIENT] nao foi possivel conectar a {host}:{port}")
    return connections


def request_block_persistent(sock, block_id):
    """
    Solicita block_id pela conexao persistente sock.
    Retorna os dados do bloco ou None (NOHAVE ou erro de conexao).
    """
    try:
        sock.sendall(struct.pack(HEADER_FMT, MSG_REQUEST, block_id, 0))
        resp_hdr = recv_exact(sock, HEADER_SIZE)
        msg_type, _, length = struct.unpack(HEADER_FMT, resp_hdr)
        if msg_type == MSG_DATA and length > 0:
            return recv_exact(sock, length)
    except Exception:
        pass
    return None


def run_client(neighbors, meta, blocks, block_registry, lock,
               done_event, output_dir, my_port):
    """
    Thread do cliente.

    1. Conecta-se a TODOS os vizinhos configurados no inicio
       (conexoes TCP persistentes — uma por vizinho).
    2. Solicita blocos faltantes iterando sobre os vizinhos em
       round-robin, reutilizando sempre a mesma conexao.
    3. Ao receber um bloco, registra-o imediatamente: o servidor
       (rodando em paralelo) ja o disponibiliza para outros peers.
    """
    total   = meta['total_blocks']
    t_start = time.time()

    time.sleep(0.5)   # aguarda servidores dos vizinhos subirem

    # --- Estabelece conexoes persistentes com todos os vizinhos ---
    connections = connect_to_neighbors(neighbors)
    if not connections:
        print("[CLIENT] nenhum vizinho disponivel — encerrando.")
        done_event.set()
        return

    conn_idx = 0   # indice para round-robin

    while not done_event.is_set():
        with lock:
            missing = [i for i in range(total) if not block_registry.get(i, False)]

        if not missing:
            break

        block_id = missing[0]
        got = False

        # Tenta cada vizinho em ordem round-robin
        for i in range(len(connections)):
            idx = (conn_idx + i) % len(connections)
            host, port, sock = connections[idx]
            data = request_block_persistent(sock, block_id)
            if data is not None:
                with lock:
                    blocks[block_id]         = data
                    block_registry[block_id] = True
                pct = (total - len(missing) + 1) / total * 100
                print(f"[CLIENT] bloco {block_id:>5}/{total-1}"
                      f"  ({pct:.1f}%)  <- {host}:{port}")
                conn_idx = (idx + 1) % len(connections)
                got = True
                break

        if not got:
            time.sleep(0.2)

    # Fecha conexoes persistentes
    for _, _, s in connections:
        try:
            s.close()
        except Exception:
            pass

    elapsed = time.time() - t_start
    assemble_file(meta, blocks, output_dir, elapsed, my_port)
    done_event.set()


# ---------------------------------------------------------------
# Remontagem e verificacao
# ---------------------------------------------------------------

def assemble_file(meta, blocks, output_dir, elapsed, my_port=0):
    filename = meta['filename']
    prefix   = f"p{my_port}_" if my_port else ""
    out_path = os.path.join(output_dir, 'received_' + prefix + filename)

    print(f"\n[ASSEMBLE] remontando {filename} ...")
    os.makedirs(output_dir, exist_ok=True)
    with open(out_path, 'wb') as f:
        for i in range(meta['total_blocks']):
            f.write(blocks[i])

    # Garante tamanho exato (ultimo bloco pode ser menor)
    with open(out_path, 'r+b') as f:
        f.truncate(meta['file_size'])

    computed = sha256_of_file(out_path)
    expected = meta['sha256']
    ok       = computed == expected

    speed_kb = (meta['file_size'] / 1024) / elapsed if elapsed > 0 else 0
    print(f"[ASSEMBLE] arquivo : {out_path}  ({meta['file_size']} bytes)")
    print(f"[ASSEMBLE] tempo   : {elapsed:.3f} s  ({speed_kb:.1f} KB/s)")
    print(f"[ASSEMBLE] sha256  : {'OK' if ok else 'ERRO!'}")
    if not ok:
        print(f"  esperado : {expected}")
        print(f"  obtido   : {computed}")
        sys.exit(1)


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description='P2P File Transfer')
    p.add_argument('--port',       type=int, default=0,    help='Porta de escuta deste peer')
    p.add_argument('--meta',       required=True,           help='Arquivo de metadados (.json)')
    p.add_argument('--file',       default=None,            help='Arquivo original (modo seeder)')
    p.add_argument('--block-size', type=int, default=1024, help='Tamanho do bloco em bytes')
    p.add_argument('--neighbors',  nargs='*', default=[],  help='Vizinhos: IP:PORTA ...')
    p.add_argument('--output',     default='.',            help='Diretorio para o arquivo recebido')
    p.add_argument('--meta-only',  action='store_true',    help='Apenas cria metadados e sai')
    args = p.parse_args()

    neighbors = []
    for n in args.neighbors or []:
        host, port = n.rsplit(':', 1)
        neighbors.append((host, int(port)))

    lock           = threading.Lock()
    blocks         = {}
    block_registry = {}
    done_event     = threading.Event()

    # Apenas cria metadados e sai
    if args.meta_only:
        if not args.file:
            print("--meta-only requer --file", file=sys.stderr)
            sys.exit(1)
        create_metadata(args.file, args.block_size, args.meta)
        return

    if not args.port:
        print("--port e obrigatorio", file=sys.stderr)
        sys.exit(1)

    # Seeder: cria metadados e carrega blocos
    if args.file:
        meta   = create_metadata(args.file, args.block_size, args.meta)
        blocks = load_blocks(args.file, meta)
        with lock:
            for i in blocks:
                block_registry[i] = True
        print(f"[SEEDER] {len(blocks)} blocos carregados de '{args.file}'")
    else:
        with open(args.meta) as f:
            meta = json.load(f)
        print(f"[LEECHER] '{meta['filename']}'  "
              f"{meta['total_blocks']} blocos  {meta['file_size']} bytes")

    # Inicia servidor nao-bloqueante em thread dedicada
    t_srv = threading.Thread(
        target=run_server,
        args=(args.port, blocks, block_registry, lock),
        daemon=True,
    )
    t_srv.start()

    # Leecher com vizinhos: inicia cliente
    if not args.file and neighbors:
        t_cli = threading.Thread(
            target=run_client,
            args=(neighbors, meta, blocks, block_registry,
                  lock, done_event, args.output, args.port),
        )
        t_cli.start()
        t_cli.join()
        print("[DONE] transferencia concluida.")
    else:
        print("[SEEDER] aguardando requisicoes... (Ctrl+C para encerrar)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[SEEDER] encerrando.")


if __name__ == '__main__':
    main()
