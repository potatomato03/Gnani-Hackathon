"""One key per ingredient, so Indian compositions and US label substances can be joined.

Indian packs use British and INN names ("Paracetamol", "Salbutamol"); US labels use
USAN names ("Acetaminophen", "Albuterol"). Salt and ester words are dropped from the
end of a name, unless the name starts with a cation ("Sodium Chloride"), where the
salt is the medicine.
"""
import re

# Indian or British spelling -> the name on a US label, after salt words are dropped.
SYNONYMS = {
    'paracetamol': 'acetaminophen', 'salbutamol': 'albuterol', 'levosalbutamol': 'levalbuterol',
    'glibenclamide': 'glyburide', 'frusemide': 'furosemide', 'lignocaine': 'lidocaine',
    'adrenaline': 'epinephrine', 'noradrenaline': 'norepinephrine', 'rifampicin': 'rifampin',
    'tazobactum': 'tazobactam', 'mesalazine': 'mesalamine', 'ciclosporin': 'cyclosporine',
    'isoprenaline': 'isoproterenol', 'pethidine': 'meperidine', 'phenobarbitone': 'phenobarbital',
    'orciprenaline': 'metaproterenol', 'colecalciferol': 'cholecalciferol', 'thyroxine': 'levothyroxine',
    'bendrofluazide': 'bendroflumethiazide', 'oxpentifylline': 'pentoxifylline', 'cefalexin': 'cephalexin',
    'dicycloverine': 'dicyclomine', 'clavulanate': 'clavulanic acid', 'valproate': 'valproic acid',
    'sodium valproate': 'valproic acid', 'divalproex': 'valproic acid', 'chlorphenamine': 'chlorpheniramine',
    'beclometasone': 'beclomethasone', 'betametasone': 'betamethasone', 'glyceryl trinitrate': 'nitroglycerin',
    'aciclovir': 'acyclovir', 'amfetamine': 'amphetamine', 'cromoglicate': 'cromolyn', 'sodium cromoglycate': 'cromolyn',
    'acetylsalicylic acid': 'aspirin', 'ursodeoxycholic acid': 'ursodiol', 'ispaghula': 'psyllium',
    'ispaghula husk': 'psyllium', 'hydroxypropylmethylcellulose': 'hypromellose', 'mesalazine': 'mesalamine',
    '5-aminosalicylic acid': 'mesalamine', 'vitamin d3': 'cholecalciferol', 'vitamin d2': 'ergocalciferol',
    'vitamin b1': 'thiamine', 'vitamin b6': 'pyridoxine', 'vitamin b12': 'cyanocobalamin', 'vitamin c': 'ascorbic acid',
    'vitamin b2': 'riboflavin', 'vitamin b3': 'niacinamide', 'vitamin k1': 'phytonadione', 'thiopentone': 'thiopental',
}
SPELLINGS = [('amoxycillin', 'amoxicillin'), ('sulph', 'sulf'), ('aluminium', 'aluminum'), ('oestr', 'estr')]
CATIONS = {'sodium', 'potassium', 'calcium', 'magnesium', 'zinc', 'ferrous', 'ferric', 'aluminum', 'lithium',
           'ammonium', 'silver', 'barium', 'iron'}
SALTS = CATIONS | {
    'hydrochloride', 'hcl', 'dihydrochloride', 'hydrobromide', 'sulfate', 'bisulfate', 'maleate', 'succinate',
    'tartrate', 'bitartrate', 'besylate', 'besilate', 'mesylate', 'mesilate', 'dimesylate', 'oxalate', 'fumarate',
    'hemifumarate', 'citrate', 'acetate', 'phosphate', 'dipropionate', 'propionate', 'furoate', 'valerate',
    'butyrate', 'monohydrate', 'dihydrate', 'trihydrate', 'sesquihydrate', 'hemihydrate', 'anhydrous', 'bromide',
    'nitrate', 'mononitrate', 'lactate', 'gluconate', 'hyclate', 'axetil', 'proxetil', 'medoxomil', 'cilexetil',
    'pivoxil', 'embonate', 'pamoate', 'decanoate', 'enanthate', 'cypionate', 'palmitate', 'stearate',
    'ethylsuccinate', 'estolate', 'tromethamine', 'trometamol', 'camsylate', 'xinafoate', 'tosylate', 'disodium',
    'dipotassium', 'chloride', 'carbonate', 'erbumine', 'arginine', 'hydrate', 'malate', 'benzoate', 'kit',
}


def ingredient_key(name):
    text = ' '.join(re.sub(r'[^a-z0-9 \-]', ' ', name.casefold()).split())
    for old, new in SPELLINGS:
        text = text.replace(old, new)
    if text in SYNONYMS:
        return SYNONYMS[text]
    words = text.split()
    if words and words[0] not in CATIONS:
        while len(words) > 1 and words[-1] in SALTS:
            words.pop()
    text = ' '.join(words)
    return SYNONYMS.get(text, text)


def product_composition(row):
    """An Indian Medicine Dataset row's composition. Most rows leave salt_composition empty and
    carry only the two short columns, which hold at most two ingredients."""
    full = ' '.join(row.get('salt_composition', '').split())
    if full:
        return full
    shorts = [' '.join(row.get(k, '').split()) for k in ('short_composition1', 'short_composition2')]
    return ' + '.join(s for s in shorts if s)


def ingredients_of(composition):
    """Ingredient keys of an Indian composition such as "Amoxycillin (500mg) + Clavulanic Acid (125mg)"."""
    parts = re.split(r'\s\+\s', re.sub(r'\([^)]*\)', ' ', composition))
    return {ingredient_key(p) for p in parts if p.strip()}
