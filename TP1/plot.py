"""
Gera graficos a partir dos resultados do benchmark.
Precisa de: pip install matplotlib pandas
Uso: python plot.py
"""
import pandas as pd
import matplotlib.pyplot as plt
import glob

# --- Grafico 1: Tempo medio por combinacao de threads ---

df = pd.read_csv("results.csv")

fig, ax = plt.subplots(figsize=(10, 5))

for n in sorted(df["N"].unique()):
    sub = df[df["N"] == n].copy()
    sub["label"] = sub.apply(lambda r: f"({int(r.Np)},{int(r.Nc)})", axis=1)
    ax.plot(sub["label"], sub["tempo_medio"], marker="o", label=f"N={n}")

ax.set_xlabel("(Np, Nc)")
ax.set_ylabel("Tempo medio (s)")
ax.set_title("Tempo medio de execucao - Produtor/Consumidor com Semaforos")
ax.legend()
ax.grid(True)
plt.xticks(rotation=30)
plt.tight_layout()
plt.savefig("tempo_medio.png", dpi=150)
print("Salvo: tempo_medio.png")

# --- Grafico 2: Ocupacao do buffer ao longo do tempo (um por cenario) ---

csv_files = glob.glob("occ_*.csv")
for fname in csv_files[:4]:  # limita a 4 graficos para nao poluir
    data = pd.read_csv(fname)
    plt.figure(figsize=(10, 3))
    plt.plot(data["operacao"], data["ocupacao"], linewidth=0.5)
    titulo = fname.replace("occ_", "").replace(".csv", "").replace("_", "  ")
    plt.title(f"Ocupacao do buffer - {titulo}")
    plt.xlabel("Operacao")
    plt.ylabel("Ocupacao")
    plt.tight_layout()
    out = fname.replace(".csv", ".png")
    plt.savefig(out, dpi=150)
    print(f"Salvo: {out}")
    plt.close()
