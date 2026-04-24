import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

cenarios = [
    ('occ_N1_Np1_Nc1.csv',    'N=1,  (Np,Nc)=(1,1)'),
    ('occ_N10_Np1_Nc1.csv',   'N=10, (Np,Nc)=(1,1)'),
    ('occ_N100_Np1_Nc1.csv',  'N=100, (Np,Nc)=(1,1)'),
    ('occ_N1000_Np4_Nc4.csv', 'N=1000, (Np,Nc)=(4,4)'),
]

for fname, titulo in cenarios:
    data = pd.read_csv(fname)
    plt.figure(figsize=(10, 3))
    plt.plot(data['operacao'], data['ocupacao'], linewidth=0.5)
    plt.title(titulo)
    plt.xlabel('Operacao')
    plt.ylabel('Ocupacao do buffer')
    plt.tight_layout()
    out = fname.replace('.csv', '.png')
    plt.savefig(out, dpi=150)
    plt.close()
    print('Salvo:', out)
