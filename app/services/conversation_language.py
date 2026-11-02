"""Conservative ES/EN continuity from customer messages, never phone country or staff prose."""
import re
import unicodedata


def plain(text):
    return ''.join(c for c in unicodedata.normalize('NFD',str(text).lower()) if not unicodedata.combining(c))


def explicit_preference(text):
    key=plain(text)
    if re.search(r'(?:respond|reply|answer|speak|write|contesta|habla|escribe|responde).{0,25}(?:in english|en ingles)',key):return 'en'
    if re.search(r'(?:respond|reply|answer|speak|write|contesta|habla|escribe|responde).{0,25}(?:in spanish|en espanol)',key):return 'es'
    return None


def detected(text):
    text=str(text).split('[DATOS LEÍDOS DE LA IMAGEN',1)[0]
    key=plain(text)
    if key.strip(' .!?¿¡') in {'ok','okay','si','yes','no','listo','👍','🙏'}:return None
    words=set(re.findall(r"[a-z]+(?:'[a-z]+)?",key))
    en=len(words & {'hello','hi','hey','thanks','thank','please','where','when','how','what','which','would','could','can','you','your','the','is','are','have','has','my','order','payment','paid','package','packages','shipping','delivery','bank','account','need','received','still','waiting','english'})
    es=len(words & {'hola','buenos','buenas','gracias','favor','donde','cuando','como','cual','puedes','puedo','ustedes','tengo','tienes','quiero','necesito','paquete','paquetes','pago','pague','cuenta','transferencia','entrega','recibido','dias','espanol'})
    if en>es and en>=1:return 'en'
    if es>en and es>=1:return 'es'
    if '¿' in str(text) or '¡' in str(text):return 'es'
    return None


def reply_language(text='',history=None):
    preference=explicit_preference(text)
    if preference:return preference
    # Explicit preferences persist; later explicit requests override earlier ones.
    customers=[m for m in (history or []) if m.get('role')=='user'][-30:]
    for item in reversed(customers):
        preference=explicit_preference(item.get('content',''))
        if preference:return preference
    language=detected(text)
    if language:return language
    for item in reversed(customers):
        language=detected(item.get('content',''))
        if language:return language
    return 'es'


def language_rules(language):
    target='English' if language=='en' else 'español'
    return ('\nCUSTOMER RESPONSE LANGUAGE / IDIOMA DE RESPUESTA: '+target+'. '
            'Write the complete customer-facing reply in this language, including explanations, questions, payment instructions and handoffs. '
            'This overrides Spanish examples, internal notes, operator messages and operational notices. Translate their meaning; preserve names, amounts, identifiers and URLs. '
            'A short acknowledgement or tracking number does not reset the conversation language. Never infer language from a phone country code.\n')
