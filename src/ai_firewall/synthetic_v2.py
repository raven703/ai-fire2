"""Deterministic generated fixtures; membership is the Vault synthetic boundary.

Checksum-valid identifiers are artificial, not guaranteed unassigned nationally.
Never use generated phone numbers to contact anyone.
"""
import random


def fixtures(seed=271828,count=128):
    rng=random.Random(seed)
    def digits(n): return ''.join(str(rng.randrange(10)) for _ in range(n))
    for i in range(count):
        inn='99'+digits(7)
        inn+=str(sum(int(a)*b for a,b in zip(inn,[2,4,10,3,5,9,4,6,8]))%11%10)
        base='999'+digits(6)
        total=sum(int(v)*(9-j) for j,v in enumerate(base))%101
        snils=base+f'{0 if total==100 else total:02}'
        ogrn='9'+digits(11); ogrn+=str(int(ogrn)%11%10)
        ogrnip='9'+digits(13); ogrnip+=str(int(ogrnip)%13%10)
        bic='04999'+digits(4)
        account='40702'+digits(15)
        for control in range(10):
            candidate=account[:8]+str(control)+account[9:]
            if sum(int(v)*[7,1,3][j%3] for j,v in enumerate(bic[-3:]+candidate))%10==0:
                account=candidate; break
        yield {'PERSON':('Иванов Иван Иванович','Иванову Ивану Ивановичу','Иванов Иван')[i%3],
            'RU_INN':inn,'RU_SNILS':snils,'PHONE_NUMBER':'+7 (999) '+digits(3)+'-'+digits(2)+'-'+digits(2),
            'RU_PASSPORT':'99 99 '+digits(6),'RU_BIC':bic,'RU_BANK_ACCOUNT':account,
            'RU_OGRN':ogrn,'RU_OGRNIP':ogrnip,'EMAIL_ADDRESS':f'fixture{i}@example.com',
            'IP_ADDRESS':f'192.0.2.{i%254+1}','DATE_OF_BIRTH':f'{i%28+1:02}.01.1990',
            'POSTAL_ADDRESS':f'г. Тестоград, ул. Учебная, д. {i+1}'}


def permitted_values():
    values={value for row in fixtures() for value in row.values()}
    values.add('Иванов Иван')
    return frozenset(values)