"""
Gera graficos de desempenho para o TP2 - Transferencia P2P.
Precisa de: pip install matplotlib
Uso: python plot.py
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# -------------------------------------------------------------------
# Dados extraidos dos logs (2 peers, bloco 1024 B e 4096 B)
# -------------------------------------------------------------------

arquivos   = ['File A\n10 KB', 'File A\n20 KB', 'File B\n1 MB', 'File B\n5 MB', 'File C\n10 MB']
tamanhos   = [10, 20, 1024, 5120, 10240]   # KB

tempo_1k   = [0.50,  0.51,  0.79,  3.47,   9.65]  # segundos (bloco 1 KB)
tempo_4k   = [0.50,  0.50,  0.56,  0.87,   1.54]  # segundos (bloco 4 KB)

thru_1k    = [19.8,  39.4,  1290.1,  1475.7,  1061.7]  # KB/s (bloco 1 KB)
thru_4k    = [19.8,  39.7,  1845.6,  5896.8,  6670.8]  # KB/s (bloco 4 KB)

x = np.arange(len(arquivos))
w = 0.35   # largura das barras

# -------------------------------------------------------------------
# Grafico 1 — Throughput (KB/s)
# -------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5))

b1 = ax.bar(x - w/2, thru_1k, w, label='Bloco 1 KB', color='steelblue')
b2 = ax.bar(x + w/2, thru_4k, w, label='Bloco 4 KB', color='darkorange')

ax.set_xlabel('Arquivo de teste')
ax.set_ylabel('Throughput (KB/s)')
ax.set_title('Throughput de transferência — 2 peers (Seeder + Leecher)')
ax.set_xticks(x)
ax.set_xticklabels(arquivos)
ax.legend()
ax.grid(axis='y', linestyle='--', alpha=0.6)
ax.bar_label(b1, fmt='%.0f', padding=3, fontsize=8)
ax.bar_label(b2, fmt='%.0f', padding=3, fontsize=8)

plt.tight_layout()
plt.savefig('throughput.png', dpi=150)
print('Salvo: throughput.png')
plt.close()

# -------------------------------------------------------------------
# Grafico 2 — Tempo de transferencia (s)
# -------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5))

b3 = ax.bar(x - w/2, tempo_1k, w, label='Bloco 1 KB', color='steelblue')
b4 = ax.bar(x + w/2, tempo_4k, w, label='Bloco 4 KB', color='darkorange')

ax.set_xlabel('Arquivo de teste')
ax.set_ylabel('Tempo (s)')
ax.set_title('Tempo de transferência — 2 peers (Seeder + Leecher)')
ax.set_xticks(x)
ax.set_xticklabels(arquivos)
ax.legend()
ax.grid(axis='y', linestyle='--', alpha=0.6)
ax.bar_label(b3, fmt='%.2f', padding=3, fontsize=8)
ax.bar_label(b4, fmt='%.2f', padding=3, fontsize=8)

plt.tight_layout()
plt.savefig('tempo.png', dpi=150)
print('Salvo: tempo.png')
plt.close()

# -------------------------------------------------------------------
# Grafico 3 — Ganho de throughput (4 KB / 1 KB)
# -------------------------------------------------------------------
ganho = [t4/t1 for t1, t4 in zip(thru_1k, thru_4k)]

fig, ax = plt.subplots(figsize=(10, 4))

bars = ax.bar(x, ganho, color=['#c6dbef' if g < 1.5 else '#2171b5' for g in ganho])
ax.axhline(1.0, color='red', linestyle='--', linewidth=1, label='Sem ganho (1×)')
ax.set_xlabel('Arquivo de teste')
ax.set_ylabel('Fator de ganho (×)')
ax.set_title('Ganho de throughput: bloco 4 KB vs 1 KB')
ax.set_xticks(x)
ax.set_xticklabels(arquivos)
ax.legend()
ax.grid(axis='y', linestyle='--', alpha=0.6)
ax.bar_label(bars, fmt='%.1fx', padding=3, fontsize=9)

plt.tight_layout()
plt.savefig('ganho.png', dpi=150)
print('Salvo: ganho.png')
plt.close()
