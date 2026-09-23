"""
Pacote de carga e verificação do banco CrimeMap DF.

Uso:
    python -m db.load_csv          # carrega CSV consolidado + contornos no Postgres
    python -m db.smoke_test        # valida se os totais do banco batem com o CSV
"""
