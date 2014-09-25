from random import choice

with open('nouns.txt', 'r') as nfile:
    nouns = map(str.strip, nfile.readlines())

with open('adjectives.txt', 'r') as afile:
    adjectives = map(str.strip, afile.readlines())


def gen_id():
    return '_'.join([choice(adjectives), choice(nouns)])


