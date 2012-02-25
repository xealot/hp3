

def random_password(minpairs=3, maxpairs=4):
    """Create a random password as pairs of consonants and vowels.  The
    number of "pairs" is chosen randomly between minpairs and maxpairs.
    The letters are also randomly capitalized (50/50 chance)"""
    import random, string

    vowels='aeiou'
    consonants='bcdfghjklmnpqrstvwxyz'
    password=''

    for x in range(1,random.randint(int(minpairs),int(maxpairs))):
        consonant = consonants[random.randint(1,len(consonants)-1)]
        if random.choice([1,0]):
            consonant = string.upper(consonant)
        password += consonant
        vowel = vowels[random.randint(1,len(vowels)-1)]
        if random.choice([1,0]):
            vowel = string.upper(vowel)
        password += vowel
    return password
