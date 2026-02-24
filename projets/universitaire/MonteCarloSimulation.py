import numpy as np
import numpy.random as rd
from matplotlib import pyplot as plt
from scipy.stats import norm

#Estimation loi de Bernouilli

def estimExp(N):
    L = []
    for i in range(N):
        X = rd.randint(0, 2) #pour le random il faut selectionner un intervalle [a, b+1]
        L.append(X)
    return np.mean(L) #Faire la moyenne des X de la liste L

#print(estimExp(100000))

#Ici je génère des variables binomiales donc je ne dois pas les pondérer à leurs probas
#Correction trouver sur le net beaucoup plus simple

def estiExp(N):
    L = []
    for i in range(N):
        X = rd.binomial(1, 1/2)
        L.append(X)
    return np.mean(L)

#print(estiExp(100000))

#Estimer une probabilité (un dé)

def simuX(N):
    L = []
    for i in range(N):
        X = rd.randint(1, 7)
        if X == 4:
            L.append(X)
    return len(L)/N

#print(simuX(100000))

#Simulation du pricing d'une option européenne ; ce code peut être simplifier je pense au lieu d'appeller 4 fois une fonction différente qui fait presque la même chose

# Initialisation des paramètres 

S0 = 100
sigma = 0.2
T = 1
r = 0.03
N = 100000
K = 100

#Calculer le prix d'une option européenne d'après les formules disponibles en ligne
"""
def Payoff(S0, K, T, r, sigma, N, seed):
    rd.seed(seed)
    P = []
    for i in range(N):
        Zi = rd.normal(0, 1) #Simulation d'une loi normale centrée réduite
        St = S0 * np.exp((r - 1/2*sigma**2)*T + sigma*Zi*np.sqrt(T))
        Pi = max(St - K, 0)
        P.append(Pi)
    return np.mean(P)

def PBar(S0, K, T, r, sigma, N, seed):
    Pbar = Payoff(S0, K, T, r, sigma, N, seed)
    return np.exp(-r*T)*Pbar

print(PBar(S0, K, T, r, sigma, N, seed))

"""

#Version plus simple et moins lourds du payoff

def CallMC(S0, K, T, r, sigma, N, seed=None):
    rng = np.random.default_rng(seed) #Initialisation du générateur de nombres aléatoires pour obtenir des résultats reproductibles avec la seed 123
    Z = rng.normal(0, 1, N) #Simulation d'une loi normale centrée réduite pour N variables
    St = S0 * np.exp((r - 1/2*sigma**2)*T + sigma*Z*np.sqrt(T)) # Calcul de St pour chaque Zi
    Pi = np.maximum(St - K, 0) #Calcul du payoff pour chaque St
    Y = Pi * np.exp(-r*T) #Ajout du payoff pondéré à la liste Y
    V0 = np.mean(Y) #Calcul du prix de l'option
    s = ((1/(N-1))*np.sum((Y - V0)**2))**(1/2) #Calcul de la variance de Y
    SE = s / np.sqrt(N) #Calcul de l'erreur standard
    IC_bas = V0 - 1.96*SE
    IC_haut = V0 + 1.96*SE
    return V0, IC_bas, IC_haut, SE

#print(CallMC(S0, K, T, r, sigma, N))

def PutMC(S0, K, T, r, sigma, N, seed=None):
    rng = np.random.default_rng(seed) #Initialisation du générateur de nombres aléatoires pour obtenir des résultats reproductibles avec la seed 123
    Z = rng.normal(0, 1, N) #Simulation d'une loi normale centrée réduite pour N variables
    St = S0 * np.exp((r - 1/2*sigma**2)*T + sigma*Z*np.sqrt(T)) # Calcul de St pour chaque Zi
    Pi = np.maximum(K - St, 0) #Calcul du payoff pour chaque St
    Y = Pi * np.exp(-r*T) #Ajout du payoff pondéré à la liste Y
    V0 = np.mean(Y) #Calcul du prix de l'option
    s = ((1/(N-1))*np.sum((Y - V0)**2))**(1/2) #Calcul de la variance de Y
    SE = s / np.sqrt(N) #Calcul de l'erreur standard
    IC_bas = V0 - 1.96*SE
    IC_haut = V0 + 1.96*SE
    return V0, IC_bas, IC_haut, SE

#print(PutMC(S0, K, T, r, sigma, N))

"""
for i in range (100000, 10000000, 100000):
    print(CallMC(S0, K, T, r, sigma, i))

On remarque que les prix convergent vers la valeur analytique dans le modèle de Black-Scholes de l'option qui est de 9.41

"""

#Avec réduction de variance forme antithétique

def ACallMC(S0, K, T, r, sigma, N, seed=None):
    rng = np.random.default_rng(seed) #Initialisation du générateur de nombres aléatoires pour obtenir des résultats reproductibles avec la seed 123
    Z = rng.normal(0, 1, N) #Simulation d'une loi normale centrée réduite pour N variables
    St = S0 * np.exp((r - 1/2*sigma**2)*T + sigma*Z*np.sqrt(T)) # Calcul de St pour chaque Zi
    Sn = S0 * np.exp((r - 1/2*sigma**2)*T - sigma*Z*np.sqrt(T))
    Pplus = np.maximum(St - K, 0) #Calcul du payoff pour chaque St
    Pmoins = np.maximum(Sn - K, 0)
    Pi = (Pplus + Pmoins) / 2
    Y = Pi * np.exp(-r*T) #Ajout du payoff pondéré à la liste Y
    V0 = np.mean(Y) #Calcul du prix de l'option
    s = ((1/(N-1))*np.sum((Y - V0)**2))**(1/2) #Calcul de la variance de Y
    SE = s / np.sqrt(N) #Calcul de l'erreur standard
    IC_bas = V0 - 1.96*SE
    IC_haut = V0 + 1.96*SE
    return V0, IC_bas, IC_haut, SE

def APutMC(S0, K, T, r, sigma, N, seed=None):
    rng = np.random.default_rng(seed) #Initialisation du générateur de nombres aléatoires pour obtenir des résultats reproductibles avec la seed 123
    Z = rng.normal(0, 1, N) #Simulation d'une loi normale centrée réduite pour N variables
    St = S0 * np.exp((r - 1/2*sigma**2)*T + sigma*Z*np.sqrt(T)) # Calcul de St pour chaque Zi
    Smoins = S0 * np.exp((r - 1/2*sigma**2)*T - sigma*Z*np.sqrt(T))
    PPlus = np.maximum(K - St, 0) #Calcul du payoff pour chaque St
    Pmoins = np.maximum(K - Smoins, 0)
    Pi = (PPlus + Pmoins) / 2   
    Y = Pi * np.exp(-r*T) #Ajout du payoff pondéré à la liste Y
    V0 = np.mean(Y) #Calcul du prix de l'option
    s = ((1/(N-1))*np.sum((Y - V0)**2))**(1/2) #Calcul de la variance de Y
    SE = s / np.sqrt(N) #Calcul de l'erreur standard
    IC_bas = V0 - 1.96*SE
    IC_haut = V0 + 1.96*SE
    return V0, IC_bas, IC_haut, SE

print(ACallMC(S0, K, T, r, sigma, N))
print(APutMC(S0, K, T, r, sigma, N))

#Tracer les Payoff de nos options :

def TraceCallMC(S0, K, T, r, sigma, N):
    fig = plt.figure()
    axis = fig.add_subplot(1, 1, 1, aspect="auto")
    X = np.arange(1000, N + 1, 5000) #On crée un intervalle d'entier de 1000 à N + 1 avec un pas de 5000
    Y = []
    Z = []
    W = []
    for i in X:
        Yi, Zi, Wi, _ = CallMC(S0, K, T, r, sigma, i)
        W.append(Wi)
        Z.append(Zi)
        Y.append(Yi) #On ajoute le prix de l'option pour chaque N et en ajoutant [0] ça prend simplement le prix de l'option
    axis.plot(X , Y, label ="Convergence du prix Monte Carlo (call)", linestyle = " ", marker = "x", markersize = 2)
    axis.plot(X , Z, label ="IC 95% borne basse", linestyle = "-", marker = "o", markersize = 2)
    axis.plot(X , W, label ="IC 95% borne haute", linestyle = "-", marker = "o", markersize = 2)
    axis.legend()
    axis.grid()
    plt.show()


def TracerPutMC(S0, K, T, r, sigma, N):
    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1, aspect="auto")
    X = np.arange(1000, N + 1, 5000) #On crée un intervalle d'entier de 1000 à N + 1 avec un pas de 5000
    Y = []
    Z = []
    W = []
    for i in X:
        Yi, Zi, Wi, _ = PutMC(S0, K, T, r, sigma, i)
        W.append(Wi)
        Z.append(Zi)
        Y.append(Yi) #On ajoute le prix de l'option pour chaque N et en ajoutant [0] ça prend simplement le prix de l'option
    ax.plot(X , Y, label ="Convergence du prix Monte Carlo put", linestyle = " ", marker = "x", markersize = 2)
    ax.plot(X , Z, label ="IC 95% borne basse", linestyle = "-", marker = "o", markersize = 2)
    ax.plot(X , W, label ="IC 95% borne haute", linestyle = "-", marker = "o", markersize = 2)
    ax.legend()
    ax.grid()
    plt.show()

TraceCallMC(S0, K, T, r, sigma, N)
TracerPutMC(S0, K, T, r, sigma, N)

"""

Tracer l'écart entre la version antithétique de Monte Carlo et la version normal

"""
def CompTraceCall(S0, K, T, r, sigma, N, seed=None):
    fig = plt.figure()
    axe = fig.add_subplot(1, 1, 1, aspect="auto")
    X = np.arange(1000, N + 1, 5000) #On crée un intervalle d'entier de 1000 à N + 1 avec un pas de 5000
    Y = []
    Z = []
    for i in X:
        Yi, _, _, _ = CallMC(S0, K, T, r, sigma, i)
        Zi, _, _, _ = ACallMC(S0, K, T, r, sigma, i)
        Z.append(Zi)
        Y.append(Yi) #On ajoute le prix de l'option pour chaque N et en ajoutant [0] ça prend simplement le prix de l'option
    axe.plot(X , Y, label ="Normale", linestyle = "dashdot", marker = "x", markersize = 2)
    axe.plot(X , Z, label ="Antithétique", linestyle = "-", marker = "o", markersize = 2)
    axe.legend()
    axe.set_title(label = "Ecart entre la version antithétique de Monte Carlo et la version normale")
    axe.grid()
    plt.show()

def CompTracePut(S0, K, T, r, sigma, N):
    fig = plt.figure()
    axe = fig.add_subplot(1, 1, 1, aspect="auto")
    X = np.arange(1000, N + 1, 5000) #On crée un intervalle d'entier de 1000 à N + 1 avec un pas de 5000
    Y = []
    Z = []
    for i in X:
        Yi, _, _, _ = PutMC(S0, K, T, r, sigma, i)
        Zi, _, _, _ = APutMC(S0, K, T, r, sigma, i)
        Z.append(Zi)
        Y.append(Yi) #On ajoute le prix de l'option pour chaque N et en ajoutant [0] ça prend simplement le prix de l'option
    axe.plot(X , Y, label ="Normale", linestyle = "dashdot", marker = "x", markersize = 2)
    axe.plot(X , Z, label ="Antithétique", linestyle = "-", marker = "o", markersize = 2)
    axe.legend()
    axe.set_title(label = "Ecart entre la version antithétique de Monte Carlo et la version normale")
    axe.grid()
    plt.show()

CompTracePut(S0, K, T, r, sigma, N)
CompTraceCall(S0, K, T, r, sigma, N)


"""

Création de la formule de Black-Scholes pour un call et un put

"""

def BlackScholesCall(S0, K, T, r, sigma):
    d1 = (np.log(S0/K) + (r + 1/2*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    return S0*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)

def BlackScholesPut(S0, K, T, r, sigma):
    d1 = (np.log(S0/K) + (r + 1/2*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    return K*np.exp(-r*T)*norm.cdf(-d2) - S0*norm.cdf(-d1)

"""

On va maintenant comparer les résultats obtenus avec la formule de Black-Scholes en utilisant
l'ecart absolue, relatif et par rapport à notre SE.

"""

def Ecart(S0, K, T, r, sigma, N, option):
    option = option.lower().strip()

    if option == "call":
        V0, IC_bas, IC_haut, SE = CallMC(S0, K, T, r, sigma, N)
        VBS = BlackScholesCall(S0, K, T, r, sigma)
    elif option == "put":
        V0, IC_bas, IC_haut, SE = PutMC(S0, K, T, r, sigma, N)
        VBS = BlackScholesPut(S0, K, T, r, sigma)
    elif option == "acall":
        V0, IC_bas, IC_haut, SE = ACallMC(S0, K, T, r, sigma, N)
        VBS = BlackScholesCall(S0, K, T, r, sigma)
    elif option == "aput":
        V0, IC_bas, IC_haut, SE = APutMC(S0, K, T, r, sigma, N)
        VBS = BlackScholesPut(S0, K, T, r, sigma)
    else:
        raise ValueError("option doit être 'call', 'put', 'acall' ou 'aput'")

    abs_err = np.abs(V0 - VBS)
    rel_err = abs_err / V0 if V0 != 0 else np.nan
    z_err = abs_err / SE if SE != 0 else np.nan

    if IC_bas < VBS < IC_haut:
        msg = "Black-Scholes est dans l'IC 95% : estimation MC cohérente."
    else:
        msg = "Black-Scholes hors IC 95% : écart potentiellement non expliqué par l'erreur MC."

    return msg, abs_err, rel_err, z_err


print(Ecart(S0, K, T, r, sigma, N, 1))


