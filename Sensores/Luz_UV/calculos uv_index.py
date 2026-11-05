import random as rd

reference = 3.3
adc = rd.randint(0, 4095)

MV_ZERO = 0.010
MV_MAX = 1.100

def tensao():
  V = round((adc*reference)/4095, 3)
  return V

def uv():
  v = tensao()
  indice_uv = round(((v - MV_ZERO) * 10) / (MV_MAX - MV_ZERO))
  indice_uv = max(0, min(11, indice_uv))
  print(round(indice_uv, 1))

print(adc)
print(tensao())
uv()