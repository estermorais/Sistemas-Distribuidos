#!/usr/bin/env python3
"""
Transferencia de Arquivos Peer-to-Peer - TP2
Uso (seeder):  python3 peer.py --port 5000 --file arquivo.bin --meta arquivo.meta.json
Uso (leecher): python3 peer.py --port 5001 --meta arquivo.meta.json --neighbors 127.0.0.1:5000
"""

import socket
import threading
import struct
import json
import hashlib
import os
import sys
import time
import argparse

# --- Protocolo ---
# Header: type(4) + block_id(4) + length(4) = 12 bytes
MSG_REQUEST = 1  # cliente solicita bloco:  header apenas
MSG_DATA    = 2  # servidor envia bloco:    header + dados
MSG_NOHAVE  = 3  # servidor nao tem bloco: header apenas
HEADER_FMT  = '!III'
HEADER_SIZE = struct.calcsize(HEADER_FMT)  # 12 bytes


# ---------------------------------------------------------------
# Utilitarios
# ---------------------------------------------------------------

def recv_exact(sock, n):
    """Recebe exatamente n bytes, bloqueando ate completar."""
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
# Servidor (ouve e serve blocos)
# ---------------------------------------------------------------

def handle_connection(conn, addr, blocks, block_registry, lock):
    """Atende um cliente: recebe REQUEST, envia DATA ou NOHAVE."""
    tag = f"{addr[0]}:{addr[1]}"
    try:
        while True:
            header = recv_exact(conn, HEADER_SIZE)
            msg_type, block_id, length = struct.unpack(HEADER_FMT, header)
            if length > 0:
                recv_exact(conn, length)          # descarta payload inesperado

            if msg_type != MSG_REQUEST:
                continue

            with lock:
                has  = block_registry.get(block_id, False)
                data = blocks.get(block_id)

            if has and data is not None:
                resp = struct.pack(HEADER_FMT, MSG_DATA, block_id, len(data)) + data
                conn.sendall(resp)
                print(f"[SERVER] bloco {block_id} -> {tag}")
            else:
                resp = struct.pack(HEADER_FMT, MSG_NOHAVE, block_id, 0)
                conn.sendall(resp)

    except Exception:
        pass
    finally:
        conn.close()


def run_server(port, blocks, block_registry, lock):
    """Thread do servidor: aceita conexoes e despacha handlers."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', port))
    srv.listen(20)
    print(f"[SERVER] ouvindo na porta {port}")
    while True:
        try:
            conn, addr = srv.accept()
            t = threading.Thread(
                target=handle_connection,
                args=(conn, addr, blocks, block_registry, lock),
                daemon=True,
            )
            t.start()
        except Exception:
            break


# ---------------------------------------------------------------
# Cliente (solicita blocos aos vizinhos)
# ---------------------------------------------------------------

def request_block(host, port, block_id):
    """Abre conexao, solicita block_id, retorna dados ou None."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((host, port))
        sock.sendall(struct.pack(HEADER_FMT, MSG_REQUEST, block_id, 0))

        resp_hdr = recv_exact(sock, HEADER_SIZE)
        msg_type, _, length = struct.unpack(HEADER_FMT, resp_hdr)

        if msg_type == MSG_DATA and length > 0:
            data = recv_exact(sock, length)
            sock.close()
            return data
        sock.close()
    except Exception:
        pass
    return None


def run_client(neighbors, meta, blocks, block_registry, lock, done_event, output_dir, my_port):
    """Thread do cliente: pede blocos faltantes ate completar o arquivo."""
    total  = meta['total_blocks']
    t_start = time.time()

    time.sleep(0.5)   # aguarda servidor dos vizinhos inicializarem

    while not done_event.is_set():
        with lock:
            missing = [i for i in range(total) if not block_registry.get(i, False)]

        if not missing:
            break

        block_id = missing[0]
        got = False

        for host, port in neighbors:
            data = request_block(host, port, block_id)
            if data is not None:
                with lock:
                    blocks[block_id]        = data
                    block_registry[block_id] = True
                pct = (total - len(missing) + 1) / total * 100
                print(f"[CLIENT] bloco {block_id:>5}/{total-1}  ({pct:.1f}%)  <- {host}:{port}")
                got = True
                break

        if not got:
            time.sleep(0.2)

    elapsed = time.time() - t_start
    assemble_file(meta, blocks, output_dir, elapsed, my_port)
    done_event.set()


# ---------------------------------------------------------------
# Remontagem e verificacao
# ---------------------------------------------------------------

def assemble_file(meta, blocks, output_dir, elapsed, my_port=0):
    filename = meta['filename']
    prefix = f"p{my_port}_" if my_port else ""
    out_path = os.path.join(output_dir, 'received_' + prefix + filename)

    print(f"\n[ASSEMBLE] remontando {filename} ...")
    os.makedirs(output_dir, exist_ok=True)
    with open(out_path, 'wb') as f:
        for i in range(meta['total_blocks']):
            f.write(blocks[i])

    # garante tamanho exato (ultimo bloco pode ter padding)
    with open(out_path, 'r+b') as f:
        f.truncate(meta['file_size'])

    computed = sha256_of_file(out_path)
    expected = meta['sha256']
    ok = computed == expected

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
    p.add_argument('--port',       type=int, default=0,      help='Porta de escuta deste peer')
    p.add_argument('--meta',       required=True,             help='Arquivo de metadados (.json)')
    p.add_argument('--file',       default=None,              help='Arquivo original (modo seeder)')
    p.add_argument('--block-size', type=int, default=1024,   help='Tamanho do bloco em bytes')
    p.add_argument('--neighbors',  nargs='*', default=[],    help='Vizinhos: IP:PORTA ...')
    p.add_argument('--output',     default='.',              help='Diretorio para o arquivo recebido')
    p.add_argument('--meta-only',  action='store_true',      help='Apenas cria metadados e sai')
    args = p.parse_args()

    neighbors = []
    for n in args.neighbors or []:
        host, port = n.rsplit(':', 1)
        neighbors.append((host, int(port)))

    lock           = threading.Lock()
    blocks         = {}
    block_registry = {}
    done_event     = threading.Event()

    # --- Apenas cria metadados e sai ---
    if args.meta_only:
        if not args.file:
            print("--meta-only requer --file", file=sys.stderr); sys.exit(1)
        create_metadata(args.file, args.block_size, args.meta)
        return

    if not args.port:
        print("--port e obrigatorio", file=sys.stderr); sys.exit(1)

    # --- Seeder: cria meta e carrega blocos ---
    if args.file:
        meta   = create_metadata(args.file, args.block_size, args.meta)
        blocks = load_blocks(args.file, meta)
        with lock:
            for i in blocks:
                block_registry[i] = True
        print(f"[SEEDER] {len(blocks)} blocos carregados de '{args.file}'")

    # --- Leecher: le meta existente ---
    else:
        with open(args.meta) as f:
            meta = json.load(f)
        print(f"[LEECHER] '{meta['filename']}'  {meta['total_blocks']} blocos  {meta['file_size']} bytes")

    # inicia servidor (sempre)
    t_srv = threading.Thread(
        target=run_server,
        args=(args.port, blocks, block_registry, lock),
        daemon=True,
    )
    t_srv.start()

    # leecher com vizinhos: inicia cliente
    if not args.file and neighbors:
        t_cli = threading.Thread(
            target=run_client,
            args=(neighbors, meta, blocks, block_registry, lock, done_event, args.output, args.port),
        )
        t_cli.start()
        t_cli.join()
        print("[DONE] transferencia concluida.")

    # seeder: aguarda
    else:
        print("[SEEDER] aguardando requisicoes... (Ctrl+C para encerrar)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[SEEDER] encerrando.")


if __name__ == '__main__':
    main()
