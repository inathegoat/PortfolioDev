# -*- coding: utf-8 -*-
import numpy as np
import matplotlib as mpl
from matplotlib import pyplot as plt
import matplotlib.animation as animation


"""
import numpy as np
import matplotlib as mpl
from matplotlib import pyplot as plt

N = 50
X = np.linspace(0, 2*np.pi, N)
Y = np.sin(X)

print(X)
print(Y)

plt.plot(X, Y)

fig = plt.figure()
axis = fig.add_subplot(1, 1, 1, aspect="equal")
#axis.plot(X, Y, label='sin')
axis.plot(X, Y, linestyle = " ", marker = "o", markersize = 2)
axis.legend()
axis.grid()

#-------------------{Exercice Complémentaire}------------------------------

import numpy as np
import matplotlib as mpl
from matplotlib import pyplot as plt

N = 3000
K = 5
T = np.linspace(0, 3, N)
F = [ -(2/np.pi)*((-1)**k/k)*np.sin(2*np.pi*k*T) for k in range(1,6) ] 
s = sum(F)

fig = plt.figure()
axis = fig.add_subplot(1, 1, 1, aspect="equal")

for k in range(K):
    
    axis.plot(T, F[k])
axis.legend()
axis.grid()

axis.plot(T, s, color='black')


#----------------{Exercice 1}-------------------

a = [1, 2, 3 , -4]
print(a+a)

b = [5, -7, 9, 11]
v = np.array(a)
A = np.array([1, 2, 3 , -4])
M = np.array([a, b, [0, 0, 0, 2]])

print(v, A, M, type(a), type(v), type(A))
print(np.shape(v) , np.shape(A), np.shape(M), np.shape(M.T), np.size(M))
w = v + 2*v
v3 = v**3
C = v + a

print(w, v3, C)

Mv = M.dot(v)
N = Mv.dot(M)
MAt = M.dot(A.T)
M.dot(A)
print(Mv, N, MAt, M.dot(A))
print(A*v)
print(v.T, np.shape(v.T))
E = np.eye(4, k = 1)
print(M)
print(M[1:,3])
print(np.eye(5))
print(E)




#np.shape = la dimension de la matrice
#np.array = matrice de n lignes
#np.size = le nombre d'élément
#np.shape(M.T) = T renvoie la transposée de la matrice M
#M.dot(A) = produit de la matrice A et M
#M[x,y] = affiche le nombre à la ligne x et colonne y
#M[x,:] = renvoie la x-ieme ligne
#M[x:,y] = renvoie les nombres de la y-ieme colonne après la x-ieme ligne
#np.zeros(n) = renvoie une matrice 1 dimension de n zéros
#np.eye(n) = renvoie une matrice identitée
#np.linspace(x, y, z) = renvoie une matrice commençant à x allant jusqu'à y en ayant z valeurs au total en additionnant le même nombre

#------------------------{Exercice 3}------------------------------

M = [1, 2, 3, 4]

def matrice(M):
    n = len(M)
    Z = M+M
    C = 0
    s = - (len(M) + 1)
    for i in Z:
        s+=1
        N = np.ones(n)*i
        I = np.eye(n, k=s)
        C = C + I * N   
    return C

        
res = matrice([1, 2, 3, 4, 5, 6])
print(res)


#2) 

def Vandermond(L):
    M = np.array(L)
    n = len(M)
    X= np.zeros([n,n])
    P = M + X

    for i in range(n):
        for k in range(n): 
            X[i,k] =  P[i,k]**i 
        
    return X

res = Vandermond([1, 2, 3, 4])
print(res)
Det = np.linalg.det(res)
print(Det)

def verif(M):
    V = np.linalg.det(Vandermond(M))
    r = 1
    n = len(M)
    for j in range(1, n):
        for i in range(j):
            r = r * ( M[j] - M[i] )
    return V, r

res = verif([1, 2, 3.2, 4])
print(res)

#---------------------------{Exercice 4}------------------------------


def plotSommeSin(A):
    X = np.linspace(-A, A, 10000)
    Y = np.sin(X)
    Y2 = np.sin(X) + np.sin(2*X)
    fig = plt.figure()
    axis = fig.add_subplot(1, 1, 1)
    axis.plot(X, Y)
    axis.plot(X, Y2)
    plt.show()
    return None

res = plotSommeSin(5*np.pi)
print(res)

def plotSommeSin2(N, A):
    Y = 0
    X = np.linspace(-A, A, 500000)
    for k in range(1, N+1):
        Y = Y + (np.sin(X*k))/k
    plt.plot(X,Y, label= "Sinus")
    plt.ylabel("Ordonnées")
    plt.xlabel("Abscisse")
    plt.title("Somme Sinus")
    plt.grid()
    plt.legend()
    return None


res = plotSommeSin2(50, 5*np.pi)
print(res)

#-------------------------{Exercice 5}------------------------


def plotLemniscates(a):
    fig = plt.figure()
    axis = fig.add_subplot(1, 1, 1)
    N = 1000
    S = np.linspace(0,2*np.pi, N)
    x = np.sqrt(2)*np.cos(S)/((np.sin(S))**2 +1)
    y = x*np.sin(S)
    for i in a:
        axis.plot(i*x, i*y, label = f'a = {i}')
    axis.legend()
    plt.title("Lemniscates")

res = plotLemniscates([15, 12, 24.5, 26.5])
print(res)
"""
#------------------{Exercice Complémentaire}-------------------
# Construire une matrice P de taille NxN et construire P tels que P[i,j] > 0 et somme de i = 0 à N-1 P[i,j] = 1

    

