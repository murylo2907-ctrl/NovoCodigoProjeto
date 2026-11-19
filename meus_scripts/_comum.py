"""Funções usadas por todos os scripts desta pasta."""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SIMULADOR = RAIZ / "src" / "clasher_new"


def preparar(src=None):
    """Deixa o simulador importável e entra na pasta dele.

    O simulador abre os arquivos .json por caminho relativo, então todo script
    precisa rodar com a pasta src/clasher_new como diretório atual.
    """
    pasta = Path(src).resolve() if src else SIMULADOR
    if not (pasta / "battle.py").is_file():
        sys.exit(f"Não achei o simulador em {pasta}. Use --src para indicar a pasta src/clasher_new.")
    sys.path.insert(0, str(pasta))
    os.chdir(pasta)
    return pasta


def resolver_estrategia(nome):
    """Aceita um nome curto (human, split...), uma função ou uma classe de strategies.py."""
    import strategies
    if nome in strategies.STRATEGIES:
        return strategies.STRATEGIES[nome]
    obj = getattr(strategies, nome, None)
    if obj is None:
        opcoes = ", ".join(list(strategies.STRATEGIES) + ["HumanStyleOpponent", "StackedPushOpponent",
                                                           "CardCountingOpponent"])
        sys.exit(f"Estratégia desconhecida: {nome}. Opções: {opcoes}")
    return obj() if isinstance(obj, type) else obj
