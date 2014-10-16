from random import choice

with open('name-data/nouns.txt', 'r') as nfile:
    nouns = map(str.strip, nfile.readlines())

with open('name-data/adjectives.txt', 'r') as afile:
    adjectives = map(str.strip, afile.readlines())


def gen_id():
    return '_'.join([choice(adjectives), choice(nouns)])


