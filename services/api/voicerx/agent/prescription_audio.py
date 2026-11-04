"""Read the entire approved prescription through fixed language templates, never an LLM translation.

Brand/composition/strength, dose, timing, route, food, duration, start and stopped medicines retain their
separate approved meanings. Draft language wording remains visibly and audibly pending review.
"""
from pathlib import Path
import re
import yaml

from ..contracts.medication import AsNeeded, Frequency, Grid, Taper
from ..pipeline.assemble import content_hash, product_label
from .gate import GateRefused

LANGUAGES = {'en-IN': 'English', 'hi-IN': 'Hindi', 'ta-IN': 'Tamil', 'te-IN': 'Telugu', 'gu-IN': 'Gujarati'}
EXTRA = {
 'en-IN': dict(intro='Your doctor-approved prescription.', ask='not stated; ask the doctor', dose='Dose', timing='Schedule',
               route='Route', food='Food', duration='Duration', start='Start', today='today', tomorrow='tomorrow',
               date='from {date}', week='{n} times a week; exact times not stated', unspecified='exact times not stated',
               then='then', stop='Stopped by the doctor', action='Prescription action',
               actions={'start':'start','change':'change','continue':'continue'}, note='',
               routes={'oral':'by mouth','inhaled':'inhaled','topical':'on the skin'}),
 'hi-IN': dict(intro='डॉक्टर द्वारा स्वीकृत दवा की जानकारी।', ask='नहीं बताया गया; डॉक्टर से पूछें', dose='खुराक', timing='समय',
               route='लेने का तरीका', food='भोजन', duration='अवधि', start='शुरुआत', today='आज', tomorrow='कल', date='{date} से',
               week='हफ़्ते में {n} बार; निश्चित समय नहीं बताया गया', unspecified='निश्चित समय नहीं बताया गया', then='फिर',
               stop='डॉक्टर ने बंद की', action='दवा का निर्देश', actions={'start':'शुरू करें','change':'बदली गई','continue':'जारी रखें'},
               note='इस अनुवाद की अभी जाँच नहीं हुई है।', routes={'oral':'मुँह से','inhaled':'साँस के साथ','topical':'त्वचा पर'}),
 'ta-IN': dict(intro='மருத்துவர் ஒப்புதல் அளித்த மருந்துச் சீட்டு.', ask='குறிப்பிடப்படவில்லை; மருத்துவரிடம் கேளுங்கள்', dose='அளவு', timing='நேரம்',
               route='பயன்படுத்தும் வழி', food='உணவு', duration='கால அளவு', start='தொடக்கம்', today='இன்று', tomorrow='நாளை', date='{date} முதல்',
               week='வாரத்திற்கு {n} முறை; சரியான நேரம் குறிப்பிடப்படவில்லை', unspecified='சரியான நேரம் குறிப்பிடப்படவில்லை', then='பின்னர்',
               stop='மருத்துவர் நிறுத்தியது', action='மருந்து அறிவுரை', actions={'start':'தொடங்கவும்','change':'மாற்றப்பட்டது','continue':'தொடரவும்'},
               note='இந்த மொழிபெயர்ப்பு இன்னும் சரிபார்க்கப்படவில்லை.', routes={'oral':'வாய் வழியாக','inhaled':'உள்ளிழுக்கவும்','topical':'தோலில்'}),
 'te-IN': dict(intro='వైద్యుడు ఆమోదించిన మందుల సూచనలు.', ask='చెప్పలేదు; వైద్యుడిని అడగండి', dose='మోతాదు', timing='సమయం',
               route='వాడే విధానం', food='భోజనం', duration='వ్యవధి', start='ప్రారంభం', today='ఈరోజు', tomorrow='రేపు', date='{date} నుండి',
               week='వారానికి {n} సార్లు; ఖచ్చితమైన సమయం చెప్పలేదు', unspecified='ఖచ్చితమైన సమయం చెప్పలేదు', then='తరువాత',
               stop='వైద్యుడు ఆపిన మందు', action='మందు సూచన', actions={'start':'ప్రారంభించండి','change':'మార్చబడింది','continue':'కొనసాగించండి'},
               note='ఈ అనువాదం ఇంకా సమీక్షించబడలేదు.', routes={'oral':'నోటి ద్వారా','inhaled':'పీల్చడం ద్వారా','topical':'చర్మంపై'}),
 'gu-IN': dict(intro='ડૉક્ટર દ્વારા મંજૂર કરેલી દવાઓની સૂચનાઓ.', ask='જણાવ્યું નથી; ડૉક્ટરને પૂછો', dose='માત્રા', timing='સમય',
               route='લેવાની રીત', food='ભોજન', duration='સમયગાળો', start='શરૂઆત', today='આજે', tomorrow='આવતીકાલે', date='{date} થી',
               week='અઠવાડિયામાં {n} વખત; ચોક્કસ સમય જણાવ્યો નથી', unspecified='ચોક્કસ સમય જણાવ્યો નથી', then='પછી',
               stop='ડૉક્ટરે બંધ કરેલી દવા', action='દવાની સૂચના', actions={'start':'શરૂ કરો','change':'બદલેલી','continue':'ચાલુ રાખો'},
               note='આ અનુવાદની હજી સમીક્ષા થઈ નથી.', routes={'oral':'મોઢા દ્વારા','inhaled':'શ્વાસ દ્વારા','topical':'ત્વચા પર'}),
}
ENGLISH = dict(units={}, slots=dict(zip('maen',('morning','afternoon','evening','night'))),
               food={'after_food':'after food','before_food':'before food','with_food':'with food','empty_stomach':'empty stomach'},
               frequency='{n} times a day', as_needed='when needed', as_needed_max='when needed, at most {n} times a day',
               duration={'day':'{n} days','week':'{n} weeks','month':'{n} months'})


def requested_voice(text=None, button=None):
    if button == 'menu_voice':
        return True
    value = re.sub(r'\s+', ' ', (text or '').strip().lower()).strip('.!?')
    return value in ('voice','audio','voice note','prescription voice','prescription audio','read prescription',
                     'हिंदी में सुनाओ','दवा सुनाओ','आवाज में बताओ') or bool(re.fullmatch(
                         r'(?:voice|audio|prescription voice|prescription audio) (?:in )?(?:hindi|english|tamil|telugu|gujarati)', value))


def requested_language(text, native):
    for code, label in LANGUAGES.items():
        if re.search(r'\b' + label.lower() + r'\b', (text or '').lower()):
            return code
    return native


def prescription_text(approved, language):
    if approved.status != 'approved' or content_hash(approved) != approved.content_hash:
        raise GateRefused('Only the unchanged approved prescription can be voiced.')
    if language not in LANGUAGES:
        raise GateRefused('Prescription audio is available in Hindi, English, Tamil, Telugu and Gujarati.')
    words = EXTRA[language]
    base = ENGLISH if language == 'en-IN' else yaml.safe_load((Path(__file__).parents[1] /
             'exports/templates/lang' / (language.split('-')[0] + '.yaml')).read_text(encoding='utf-8'))
    def dose(value):
        return value.amount + ' ' + base['units'].get(value.unit, value.unit) if value else words['ask']
    def duration(value):
        return base['duration'][value.unit].format(n=value.value) if value else words['ask']
    def timing(value):
        if isinstance(value, Grid):
            return ', '.join(base['slots'][k] + ': ' + getattr(value,k) for k in 'maen')
        if isinstance(value, Frequency):
            return (base['frequency'].format(n=value.times) + ', ' + words['unspecified'] if value.period == 'day'
                    else words['week'].format(n=value.times))
        if isinstance(value, AsNeeded):
            return base['as_needed_max'].format(n=value.max_per_day) if value.max_per_day else base['as_needed']
        return words['ask']
    lines = [words['intro'], approved.header.doctor_name, str(approved.header.visit_date)]
    for rx in approved.checked.medications:
        if rx.action not in ('start','change','continue','stop'):
            continue
        product = approved.products_used.get(rx.product_id)
        label = product_label(product) if product else rx.spoken_name
        if rx.action == 'stop':
            lines.append(words['stop'] + ': ' + label)
            continue
        values = [label, words['action'] + ': ' + words['actions'][rx.action]]
        if isinstance(rx.schedule, Taper):
            values.append((' ' + words['then'] + ' ').join(dose(step.dose) + ', ' + timing(step.when) + ', ' +
                                                           duration(step.duration) for step in rx.schedule.steps))
        else:
            values += [words['dose'] + ': ' + dose(rx.dose), words['timing'] + ': ' + timing(rx.schedule),
                       words['duration'] + ': ' + duration(rx.duration)]
        values += [words['route'] + ': ' + words['routes'].get(rx.route, rx.route or words['ask']),
                   words['food'] + ': ' + base['food'].get(rx.food, words['ask'])]
        start = (words['date'].format(date=rx.start.date.isoformat()) if rx.start.condition=='date' and rx.start.date
                 else words.get(rx.start.condition, words['ask']))
        values.append(words['start'] + ': ' + start)
        lines.append('. '.join(values))
    if words['note']:
        lines.append(words['note'])
    return '\n\n'.join(lines)
