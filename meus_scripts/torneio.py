"""Torneio entre as estratégias programadas do repositório (todos contra todos).

Exemplo:
    python meus_scripts/torneio.py --jogos 5

Cada par de estratégias joga `--jogos` partidas de cada lado. Mostra o ranking,
a tabela de confrontos e salva tudo em meus_scripts/resultados/torneio.json.
"""
import argparse
import itertools
import json
import random
import time

import numpy as np

import _comum

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--jogos", type=int, default=5, help="partidas por lado em cada confronto (padrão: 5)")
parser.add_argument("--src", help="pasta src/clasher_new, se não for a padrão")
args = parser.parse_args()

SAIDA = _comum.RAIZ / "meus_scripts" / "resultados" / "torneio.json"
_comum.preparar(args.src)

from environment import CREnv  # noqa: E402
from strategies import STRATEGIES  # noqa: E402


def jogar(azul, vermelho, semente):
    random.seed(semente)
    np.random.seed(semente)
    env = CREnv(opponent_model=vermelho, visualize=False)
    obs, _ = env.reset(seed=semente)
    fim = False
    while not fim:
        obs, _, fim, _, _ = env.step(azul(obs))
    return env.battle.winner


nomes = list(STRATEGIES)
vitorias = {n: 0 for n in nomes}
partidas = {n: 0 for n in nomes}
pares = {}
semente = 1000
inicio = time.perf_counter()
total_confrontos = len(nomes) * (len(nomes) - 1) // 2
for k, (a, b) in enumerate(itertools.combinations(nomes, 2), 1):
    print(f"[{k}/{total_confrontos}] {a} x {b}...", flush=True)
    ganhas_a = 0
    for lado in range(2):
        for _ in range(args.jogos):
            semente += 1
            if lado == 0:
                ganhas_a += jogar(STRATEGIES[a], STRATEGIES[b], semente) == 0
            else:
                ganhas_a += jogar(STRATEGIES[b], STRATEGIES[a], semente) == 1
    n = 2 * args.jogos
    pares[(a, b)] = ganhas_a / n
    vitorias[a] += ganhas_a
    vitorias[b] += n - ganhas_a
    partidas[a] += n
    partidas[b] += n
duracao = time.perf_counter() - inicio

print(f"\n{sum(partidas.values()) // 2} partidas em {duracao:.1f} s\n")
print("Ranking (taxa de vitória):")
for n in sorted(nomes, key=lambda n: -vitorias[n] / partidas[n]):
    print(f"  {n:<12} {vitorias[n] / partidas[n]:6.1%}  ({vitorias[n]}/{partidas[n]})")
print("\nConfronto direto (a linha vence a coluna):")
w = 12
print(" " * w + "".join(f"{n:>{w}}" for n in nomes))
for a in nomes:
    linha = []
    for b in nomes:
        if a == b:
            linha.append(f"{'-':>{w}}")
        elif (a, b) in pares:
            linha.append(f"{pares[(a, b)]:>{w}.0%}")
        else:
            linha.append(f"{1 - pares[(b, a)]:>{w}.0%}")
    print(f"{a:>{w}}" + "".join(linha))

SAIDA.parent.mkdir(parents=True, exist_ok=True)
SAIDA.write_text(json.dumps({
    "ranking": {n: vitorias[n] / partidas[n] for n in nomes},
    "confrontos": {f"{a} x {b}": v for (a, b), v in pares.items()},
}, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"\nResultados salvos em {SAIDA}")
