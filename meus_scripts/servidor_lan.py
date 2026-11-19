"""Servidor do multiplayer local, sem precisar editar o IP dentro de server.py.

Exemplo:
    python meus_scripts/servidor_lan.py

Depois abra o cliente (src/clasher_new/client_side/client.py) em dois computadores
da mesma rede, ou duas vezes no mesmo computador. No cliente, digite o IP deste
computador na rede; se for tudo no mesmo PC, digite 127.0.0.1.
"""
import argparse
import socket

import _comum

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--host", default="0.0.0.0", help="endereço para escutar (padrão: todas as interfaces)")
parser.add_argument("--porta", type=int, default=9999, help="o cliente usa 9999; só mude se mudar lá também")
parser.add_argument("--src", help="pasta src/clasher_new, se não for a padrão")
args = parser.parse_args()
_comum.preparar(args.src)

from server import GameServer  # noqa: E402

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("10.255.255.255", 1))
    meu_ip = s.getsockname()[0]
    s.close()
except OSError:
    meu_ip = "127.0.0.1"
print(f"IP deste computador na rede (provável): {meu_ip}")
print("No mesmo computador, os clientes podem usar 127.0.0.1.")
GameServer(args.host, args.porta).run()
