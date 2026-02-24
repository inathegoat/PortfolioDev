import numpy as np
import math
import matplotlib.pyplot as plt
from math import *

#==========={Exercice 1}===========

def solEquationD2R(a,b,c):
    delta = ( b / a )**2 - 4*( c / a )
    if abs(delta) < 10**(-15) * abs(c/a):
        x1 = ( -b ) / ( 2 * a )
        return [x1]
    elif delta > 0 :
        x1 = ( ( -b ) - math.sqrt(delta) )/ ( 2 * a )
        x2 = ( ( -b ) + math.sqrt(delta) )/ ( 2 * a )
        return [x1, x2]
    else :
        return("Pas de solution réelle")


L4 = [[k, 1, 10**(-k), (1/4)*10**(-2*k)] for k in range(40)]
L5 = [[k, 1, 10**(-k), (1/5)*10**(-2*k)] for k in range(40)]

print("Pour L4")
for L in L4 : 
    res = solEquationD2R(L[1], L[2], L[3])
    print(f"pour k = {L[0]} on a {res}")
    
print("Pour L5")
for L in L5 : 
    res = solEquationD2R(L[1], L[2], L[3])
    print(f"pour k = {L[0]} on a {res}")



import cmath

def solEquationD2(a, b, c):
    
    delta = b**2 - 4*a*c
    if abs(delta) < 10**(-15) * abs(c/a):
        
        x1 = ( -b ) / ( 2 * a )    
        return [x1]
    
    elif delta > 0 :
        
        x1 = ( ( -b ) - math.sqrt(delta) )/ ( 2 * a )
        x2 = ( ( -b ) + math.sqrt(delta) )/ ( 2 * a )
        return [x1, x2]
    else :

        sol1 = (-b + cmath.sqrt(delta)) / (2*a)
        sol2 = (-b - cmath.sqrt(delta)) / (2*a)
        return [sol1, sol2]


    
def solutionVersCoefficients(r1, r2):
    a = 1
    b = (r1 + r2)
    c = r1 * r2
    return a, b, c
    print(f"Les coefficients de l'équation avec racines {r1} et {r2} sont : a={a}, b={b}, c={c}")

#========{Exercice 2}===================


def euler2(n):
    S = 0
    for j in range(1, n+1):
        S += 1 / (j**2)  
    return S



def euler1(n):
    T = 0
    for i in range(1, n+1):
        for k in range(1, n+1):
            T += 1 / (i**2 + k**3)
    return T

def euler0(n):
    U = 0
    for k in range(1, n+1):
        for i in range(1, n+1):
            U += 1 / (i**2 + k**3)
    return U

#=============={Exercice 3}==============

def Liste(n):
    W = [0]
    for w in range(1, n+1):
        W.append(w**2)
        
    return W

def Liste2(n):
    Z = [z**2 for z in range(1, n+1)]
    return Z


def carre(x):
    return x**2
def Liste0(n):
    Y = [y for y in range(1,n+1)]
    Y2 = map(carre, Y)
    return list(Y2)

#========================[Exercice 4]=============================

def F(a, b):
    while b != 0:
        print(f"Avant : a = {a}, b = {b}")  # Affiche les valeurs avant l'échange
        a, b = b, a % b
        print(f"Après : a = {a}, b = {b}")  # Affiche les nouvelles valeurs après l'échange
    return a

#===================================={Remarque}================================
def surLaSommeHarmonique(borne):
    N = 1
    n = 1
    while N <= borne :
        N += 1/n
        n += 1
    return n
#============================{Exercice 5}======================================
def doublons(L):
    U = []
    for x in L :
        if x not in U:
            U.append(x)
    return U


#======================================{Exercice 6}===========================#
def eulerDecimalExactes(d, N):
    S = euler2(N)
    d = format( (S - int(S)), '.5f')
    return d

print(eulerDecimalExactes(2, 4))

def euler3(N):
    """Calcul de la somme partielle de la série 1/j^3 jusqu'à N"""
    return sum(1 / (j ** 3) for j in range(1, N + 1))

def eulerDecimalesExactes3(d):
    """Trouve la somme S et le plus petit N pour lequel S a les d premières décimales égales à celles de zeta(3)"""
    zeta3 = 1.202056903159594  # valeur approximative de zeta(3)
    str_zeta3 = f"{zeta3:.{d}f}"  # zeta(3) avec d décimales
    
    N = 1
    while True:
        S = euler3(N)
        str_S = f"{S:.{d}f}"  # S avec d décimales
        if str_S == str_zeta3:
            return S, N
        N += 1

# Exemple d'utilisation
d = 4
S, N = eulerDecimalesExactes3(d)
print(f"Pour {d} décimales, la somme est {S} et N = {N}.")

#=============================={Exercice 7}====================================

def sommeDiviseurs(n):
    """Retourne la somme des diviseurs stricts de n et la liste de ces diviseurs"""
    L = [d for d in range(1, n) if n % d == 0]  # Liste des diviseurs stricts
    s = sum(L)  # Somme des diviseurs stricts
    return s, L

# Exemple d'utilisation
n = 6
s, L = sommeDiviseurs(n)
print(f"Pour n = {n}, la somme des diviseurs stricts est {s} et les diviseurs stricts sont {L}.")


def nombresParfaits(n):
    """Retourne la liste des nombres parfaits inférieurs ou égaux à n"""
    parfaits = []
    for i in range(2, n + 1):
        somme, _ = sommeDiviseurs(i)
        if somme == i:  # Si la somme des diviseurs stricts est égale au nombre
            parfaits.append(i)
    return parfaits

# Exemple
n = 10000
parfaits = nombresParfaits(n)
print(f"Les nombres parfaits inférieurs ou égaux à {n} sont : {parfaits}")

def sommeDiviseursS(n):
    borne = int(n**.5)
    s = 1
    for j in range(2, borne):
        if n%j == 0 :
            s = s + j + n//j
            if borne**2 == n :
                s = s + borne
            return s
        


def amicaux(n):
    L = []
    for j in range(2, n+1):
        sj = sommeDiviseursS(j)
        for k in range(2, j+1):
            if k == sj :
                sk = sommeDiviseurs(k)[0]
                if j == sk :
                    L.append([j, k])

#==============================={Exercice 8}===================================

def estPremier(n):
    if [d for d in range(1, n) if n % d == 0] == [1] :
        return True
    else :
        return False

def CribleEratosthene(n):
    L = [k for k in range(2, n+1)]
    P = []
    
    while L != []:
        a = L[0]
        P.append(a)
        for k in range(1, n//a + 1):
            if a*k in L :
                L.remove(a*k)
    return P

print(CribleEratosthene(500))

P = CribleEratosthene(N)
X = [k for k in range(2, N+1)]
Y = []
YC = []

for k in X:
    s = 0
    for p in P:
        if p <= k:
            s += 1
    Y.append(k/s)
    YC.append(np.log(k))
    
print(f"P = {P}")

plt.plot(X, Y)
plt.plot(X, YC)



def Jumeaux(n):
    J = []
    M = CribleEratosthene(n)

    for j in range(1, len(M)-1):
        if M[j+1] - M[j] == 2 :
            J.append((M[j+1], M[j]))
            
    return J

print(Jumeaux(100))


#============================={Exercice 9}=====================================


p = [4, 2, 1]
n = 7



        