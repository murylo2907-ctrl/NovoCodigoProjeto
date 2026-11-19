# Clash Royale Simulator — pacote para VS Code

Este é o **simulador** de Clash Royale do Jason-XII (jasonmoonw), organizado para
você abrir no VS Code e rodar. É um motor de batalha em Python, feito para treinar
IA, com as cartas, o pathfinding e as estratégias do projeto original.

O código em `src/clasher_new/` é do autor original, sem alterações. A pasta
`meus_scripts/` tem utilitários que eu escrevi para facilitar (torneio, jogar,
gravar vídeo), e `exemplos/` tem um vídeo de uma partida já gravada.

## O que NÃO está aqui

Tirei de propósito a parte que joga no jogo de verdade: o cliente ao vivo, o hook
de memória (Frida) e o modelo usado em partidas reais. Essa parte lê a memória de
um jogo online e joga sozinha, o que vai contra as regras da Supercell. Se quiser
estudar aquilo, está no repositório original; aqui o foco é o simulador.

O modelo `cr_script_imitation_50k.zip` também não veio: ele é de uma versão antiga
e nem carrega com o código atual (depende de arquivos que o autor apagou).

## Como rodar

1. Instale o Python 3.11 ou mais novo e abra esta pasta no VS Code.
2. Crie um ambiente e instale as dependências:

   ```bash
   python -m venv .venv
   # Windows:  .venv\Scripts\activate
   # Mac/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```

   Para só testar o simulador e o torneio, bastam `numpy`, `fastcore` e `gymnasium`.
   Jogar numa janela e treinar precisam de `pygame` e `stable-baselines3` (que baixa
   o PyTorch, pesado).

3. Rode pelo painel "Run and Debug" do VS Code (as configurações já estão prontas)
   ou pelo terminal.

## Comandos

Teste de velocidade do simulador (precisa só do básico):

```bash
cd src/clasher_new
python benchmark_speed.py
```

Torneio entre as 6 estratégias programadas (da pasta raiz):

```bash
python meus_scripts/torneio.py --jogos 5
```

Jogar você mesmo contra um bot, numa janela (precisa de pygame + stable-baselines3):

```bash
python meus_scripts/jogar.py human_style_strategy
```

Assistir dois bots jogando:

```bash
python meus_scripts/jogar.py split --assistir human
```

Gravar uma partida em vídeo MP4 (precisa de Pillow + ffmpeg):

```bash
python meus_scripts/gravar_partida.py human split
```

## Observações importantes

- Os scripts do simulador abrem os arquivos `.json` por caminho relativo, então
  precisam rodar de dentro de `src/clasher_new`. Os scripts da pasta `meus_scripts/`
  já cuidam disso sozinhos.
- O simulador conhece só um baralho fixo de 8 cartas: Gigante, Cavaleiro, Mini
  P.E.K.K.A, Mosqueteira, Arqueiras, Servos, Flechas e Bola de Fogo.
- As estratégias disponíveis são: `human`, `split`, `punish`, `defensive`,
  `bridge`, `counterpush`.
- Para o multiplayer local (dois humanos na mesma rede), rode
  `python meus_scripts/servidor_lan.py` num computador e abra
  `src/clasher_new/client_side/client.py` nos dois.

## Créditos

Código do simulador: Jason-XII — https://github.com/Jason-XII/clash-royale-simulator
