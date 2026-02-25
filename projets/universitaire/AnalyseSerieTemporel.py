"""

Objectif de cette Page : Analyser statistiquement les rendements de TotalEnergies (TTE.PA) et identifier des faits stylisés (distribution, volatilité, autocorrélation, clustering).

"""

import yfinance as yf
import numpy as np
import matplotlib as mpl
from matplotlib import pyplot as plt

"""
#Test pour comprendre Yahoo Finance 

dat = yf.Ticker("MSFT")
# Crée un objet "Ticker" pour Microsoft (symbole boursier: MSFT).
# Cet objet permet d'accéder aux données financières de cette action.

dat.info
# Renvoie un dictionnaire avec des infos générales sur l'entreprise/action
# (secteur, marketCap, PE ratio, beta, etc.).

dat.calendar
# Renvoie le calendrier des événements importants (ex: date de résultats).

dat.analyst_price_targets
# Renvoie les objectifs de prix des analystes (moyenne, haut, bas, médiane).

dat.quarterly_income_stmt
# Renvoie le compte de résultat trimestriel (revenus, bénéfices, charges...).

dat.history(period='1mo')
# Renvoie l'historique de prix (OHLCV) sur 1 mois:
# Open, High, Low, Close, Volume.

dat.option_chain(dat.options[0]).calls
# dat.options[0] = première date d'échéance disponible des options.
# option_chain(...) récupère la chaîne d'options pour cette échéance.
# .calls prend uniquement les options d'achat (calls).

tickers = yf.Tickers('MSFT AAPL GOOG')
# Crée un objet multi-tickers pour Microsoft, Apple et Google.

tickers.tickers['MSFT'].info
# Accède à l'objet Ticker MSFT dans la collection, puis récupère ses infos.

yf.download(['MSFT', 'AAPL', 'GOOG'], period='1mo')
# Télécharge en une seule fois l'historique de marché des 3 actions sur 1 mois.
# Comparer plusieurs titres dans un DataFrame unique.
"""

#Application avec Total Energy entreprise du CAC40

Total = yf.download("TTE.PA", period="5y", interval="1d")["Close"]

R = Total.pct_change() # Rendement arithmétique avec les fonctions de yahoo finance
r = np.log(Total/Total.shift(1)) # Rendement logarithmique
R = R.dropna() #Supprime les éléments NaN
r = r.dropna()

#Calcul du nombre d'observation, la moyenne, la variance, ecart-type, quantiles de R et r

n, rmoy, rv, rsigma, rquant5, rquant25, rquant50, rquant75, rquant95  = len(r), r.mean(), r.var(), r.std(), r.quantile(0.05), r.quantile(0.25), r.quantile(0.50), r.quantile(0.75), r.quantile(0.95)
N, Rmoy, Rv, Rsigma, Rquant5, Rquant25, Rquant50, Rquant75, Rquant95  = len(R), R.mean(), R.var(), R.std(), R.quantile(0.05), R.quantile(0.25), R.quantile(0.50), R.quantile(0.75), R.quantile(0.95)

print("Nombre d'observations : ", n)
print("Moyenne des rendements logarithmiques : ", rmoy)
print("Variance des rendements logarithmiques : ", rv)
print("Ecart-type des rendements logarithmiques : ", rsigma)
print("Quantiles des rendements logarithmiques : ", rquant5, rquant25, rquant50, rquant75, rquant95)
print("Nombre d'observations : ", N)
print("Moyenne des rendements arithmétiques : ", Rmoy)
print("Variance des rendements arithmétiques : ", Rv)
print("Ecart-type des rendements arithmétiques : ", Rsigma)
print("Quantiles des rendements arithmétiques : ", Rquant5, Rquant25, Rquant50, Rquant75, Rquant95)



fig, axis = plt.subplots(3, 1, figsize=(10, 8), sharex=True)


# Graphique 1: Prix de clôture
axis[0].plot(Total, linestyle="-", marker="x", markersize=1, label="Prix de clôture")
axis[0].set_title("Prix de clôture de TotalEnergies")
axis[0].set_ylabel("Prix")
axis[0].grid(True)
axis[0].legend()

# Graphique 2: Rendements
axis[1].plot(R, marker="o", markersize=1, label="Rendements journaliers")
axis[1].set_title("Rendements journaliers de TotalEnergies")
axis[1].set_ylabel("Rendement")
axis[1].set_xlabel("Date")
axis[1].grid(True)
axis[1].legend()

#Graphique 3 : Rendements Log
axis[2].plot(r, marker="o", markersize=1, label="Rendements Logarithmiques")
axis[2].set_title("Rendements Logarithmiques de TotalEnergies")
axis[2].set_ylabel("Rendement Logarithmique")
axis[2].set_xlabel("Date")
axis[2].grid(True)
axis[2].legend()

plt.tight_layout()
plt.show()

# Assure une série 1D (pas un DataFrame)
r_series = r.squeeze().dropna()

# Paramètres ACF
max_lag = 150
lags = range(1, max_lag + 1)

# Graphique 4 : ACF des rendements logarithmiques
acf_vals_r = [r_series.autocorr(lag=k) for k in lags]

n = len(r_series.dropna())
borne = 1.96 / np.sqrt(n)
Int_bas = -borne
Int_haut = borne

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(list(lags), acf_vals_r, marker="o", linestyle="-", label="ACF")
ax.axhline(y=Int_bas, color="r", linestyle="--", label="Intervalle de confiance 95%")
ax.axhline(y=Int_haut, color="r", linestyle="--")
ax.axhline(y=0, color="black", linewidth=1)

ax.set_title("Autocorrélation des rendements logarithmiques")
ax.set_xlabel("Lag")
ax.set_ylabel("ACF")
ax.grid(True)
ax.legend()
plt.tight_layout()
plt.show()


# Graphique 5 : ACF des rendements logarithmiques au carré
r2_series = (r_series ** 2).dropna()
acf_vals_r2 = [r2_series.autocorr(lag=k) for k in lags]

# Taille d'échantillon pour l'IC asymptotique de l'ACF
n = len(r2_series)
borne = 1.96 / np.sqrt(n)

# IC 95% sous H0 (hypothèse d'autocorrélation nulle)
Int_bas = -borne
Int_haut = borne

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(list(lags), acf_vals_r2, marker="o", linestyle="-", label="ACF(r²)")
ax.axhline(y=Int_bas, color="r", linestyle="--", label="Intervalle de confiance 95%")
ax.axhline(y=Int_haut, color="r", linestyle="--")
ax.axhline(y=0, color="black", linewidth=1)

ax.set_title("Autocorrélation des rendements logarithmiques au carré")
ax.set_xlabel("Lag")
ax.set_ylabel("ACF")
ax.grid(True)
ax.legend()
plt.tight_layout()
plt.show()


#Graphique 6 : Histogramme des rendements

plt.hist(r, bins=50, density=True, alpha=0.6, color='g')
plt.title("Histogramme des rendements logarithmiques")
plt.xlabel("Rendement")
plt.ylabel("Densité")
plt.grid(True)
plt.show()
