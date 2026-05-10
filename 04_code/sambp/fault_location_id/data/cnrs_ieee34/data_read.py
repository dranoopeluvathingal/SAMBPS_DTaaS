#!/usr/bin/env python3
"""
Created on 10 Feb 2024
 This is an example showing how to read .mat file using python.

@author: yangjunjie
"""

import scipy.io as scio

dataDic = scio.loadmat('Case_10_1_1.mat')

sigs = dataDic['signals'] # shape: len x 70
t = dataDic['t'] # shape: len x 1

print('signal shape: ',sigs.shape)
print('time shape: ',t.shape)
