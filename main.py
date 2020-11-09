import urllib3, certifi, os, json, re, time, sys, hashlib

from googleapiclient.discovery import build
from google.cloud import storage
from bs4 import BeautifulSoup
from jinja2 import Template


CLOVER_MERCHANT_ID=os.environ['CLOVER_MERCHANT_ID']
CLOVER_TOKEN=os.environ['CLOVER_TOKEN']

CATEGORIES=['Draft', 'Beer Cans', 'Beer Bottles', 'Red Wine', 'White Wine', 
        'Sparkling Wine', 'Wine By Bottle', 'Port Tawny, Shots & Spikes', 
        'Craft Soda/NA', 'Coffee & Teas', 'Snacks']

URL_BASE='https://api.clover.com/v3/merchants/'+CLOVER_MERCHANT_ID+'/'

GOOGLE_SEARCH_API_KEY=os.getenv('GOOGLE_SEARCH_API_KEY')
GOOGLE_SEARCH_ENGINE_ID=os.getenv('GOOGLE_SEARCH_CSE')

beerCategories = ['Draft', 'Beer Cans', 'Beer Bottles']
wineCategories = ['Red Wine', 'White Wine', 'Sparkling Wine']

#env the following:
STORAGE_BUCKET=os.getenv('STORAGE_BUCKET')

http = urllib3.PoolManager()

def getAllTags():
    reqCompleted = False
    i = 0 
    tags = ''

    while not reqCompleted:
        i += 1
        res = http.request_encode_url(
                'GET',
                URL_BASE + 'tags?limit=1000',
                headers={
                    'Authorization': 'Bearer ' + CLOVER_TOKEN
                    }
                )
        if res.status == 200:
            reqCompleted = True
            tags = res.data.decode('utf-8')
        else: 
            time.sleep(i * 2)

        if i > 5: 
            sys.exit("Could not get tag information from clover")

    with open('/tmp/tagList.json', 'w') as f:
        f.writelines(tags)

    print('/tmp/tagsList.json updated')


def getBeerAdvocateInfo(name):
    name = filterName(name)
    print("Name for getBeerAdvocateInfo(): "+name)
    service = build("customsearch", "v1", developerKey=GOOGLE_SEARCH_API_KEY)
    res = service.cse().list(q=name,cx=GOOGLE_SEARCH_ENGINE_ID).execute()

    if 'items' not in res.keys():
        if 'spelling' in res.keys():
            query = res['spelling']['correctedQuery']
            res = service.cse().list(q=query,
                    cx=GOOGLE_SEARCH_ENGINE_ID).execute()


    styleText, abvText = '', ''
    
    if 'items' in res.keys():
        ba_link = res['items'][0]['link']

        r = http.request_encode_url(
                'GET',
                ba_link
                )
        
        soup = BeautifulSoup(r.data, 'html.parser')

        style = soup.find('a', title='Learn more about this style.')
        abv = soup.find_all('span', title='Percentage of alcohol by volume.')

        abvRE = re.compile('[0-9]+\.*[0-9]*%')
        for a in abv:
            if abvRE.match(a.text):
                abv = a
        
        if style ==  None:
            styleText = ''
        else:
            styleText = style.text

        if abv == [] :
            abvText = ''
        else:
            abvText = abv.text

    return styleText, abvText



def filterName(s): 
    filterList = ['€','¶','∆','•','°']
    p = re.compile('(€|¶|∆|•|°|[0-9]*\.*[0-9]+%|[0-9]*o*z|\{.*\})')
    return p.sub('', s)

def filterPrice(i):
    if type(i) == int:
        i = i/100
    elif type(i) == str:
        i = float(i)
    return ('%f' % i).rstrip('0').rstrip('.').lstrip('0')

def getInventory():
    reqCompleted = False
    i = 0 

    while not reqCompleted:
        i += 1
        r = http.request_encode_url(
                'GET',
                URL_BASE+'items?limit=1000&filter=hidden=false&expand=categories%2Ctags',
                headers={
                    'Authorization':'Bearer ' + CLOVER_TOKEN
                    }
                )
        if r.status == 200:
            reqCompleted = True
        else:
            time.sleep(i * 2)

        if i > 5: 
            sys.exit("Error: could not get invetory.")

    inventory = json.loads(r.data.decode('utf-8'))
    
    inventory_map = {}

    for i in inventory['elements']: 
        for c in i['categories']['elements']: 
            cname = c['name']
            if cname not in inventory_map.keys():
                inventory_map[cname] = []
            inventory_map[cname].append(i)
    return inventory_map



def addTag(i, tagId):
    data = {
            'elements': [
                {'item':{
                    'id': i['id']
                    },
                 'tag':{
                     'id': tagId
                     }
                 }
                ]
            }

    encoded_data = json.dumps(data).encode('utf-8')
    tagCompleted = False
    iterator = 0

    while not tagCompleted:
        iterator += 1
        r = http.request_encode_url(
                'POST',
                URL_BASE + 'tag_items',
                body=encoded_data,
                headers={
                    'Authorization': 'Bearer ' + CLOVER_TOKEN,
                    'Content-Type': 'application/json'
                    }
                )
        if r.status in range(200, 299):
            tagCompleted = True
        if r.status == 429:
            time.sleep(iterator * 2)
        if iterator > 5: 
            print("Error: Could not tag item: " +  json.dumps(i))
            print("Error: status: " + str(r.status))
            tagCompleted = True

def tagBeer(b): 
    # Does tag exist?
    tags = ''
    with open('/tmp/tagList.json') as f:
        tags = json.load(f)

    styleTagExists, abvTagExists = False, False

    for t in tags['elements']:
        if t['name'] == b['styleTag']:
            b['styleTagId'] = t['id']
        if t['name'] == b['abvTag']:
            b['abvTagId'] = t['id']

    if 'styleTagId' not in b.keys():
        b['styleTagId'] = createTag(b['styleTag'])

    if 'abvTagId' not in b.keys():
        b['abvTagId'] = createTag(b['abvTag'])

    for tagIdName in ['styleTagId', 'abvTagId']:
        addTag(b, b[tagIdName]) 

    

def createTag(tName):
    data = {
            'showInReporting': 'false',
            'name': tName
            }
    encoded_data = json.dumps(data).encode('utf-8')

    tagCompleted = False
    i = 0 
    tagId = ''

    while not tagCompleted: 
        i += 1
        r = http.request_encode_url(
                'POST',
                URL_BASE + 'tags',
                body=encoded_data,
                headers={
                    'Authorization': 'Bearer ' + CLOVER_TOKEN,
                    'Content-Type': 'application/json'
                    }
                )
        if r.status in range(200, 299):
            tagCompleted = True
            print("tag created: " + tName)
            tagId = json.loads(r.data)['id']
        if r.status == 429:
            time.sleep(i * 2)
        if i > 5: 
            print("Error: Could not create tag: " +  tName)
            tagCompleted = True
    return tagId
    


def main():
    # Compile inventory into a mapping based on categories
    inventory_map = getInventory()
   

    # Find beers with untagged info
    untaggedBeers = []

    tagAbvRE = re.compile('abv=.*')
    tagStyleRE = re.compile('style=.*')

    for c in beerCategories:
        for i in inventory_map[c]:
            tagExistsStyle = False
            tagExistsAbv = False
            for t in i['tags']['elements']:
                if tagAbvRE.match(t['name']): 
                    tagExistsAbv = True
                if tagStyleRE.match(t['name']):
                    tagExistsStyle = True
            if not tagExistsStyle or not tagExistsAbv: 
                untaggedBeers.append(i)



    # Stage Current tag information
    getAllTags()

    # Find info on untagged beers
    for b in untaggedBeers:
        style, abv = getBeerAdvocateInfo(b['name'])
        b['styleTag'] = 'style=' +style
        b['abvTag'] = 'abv=' +abv

    # Tag beers

    for b in untaggedBeers:
        tagBeer(b)
        getAllTags()

    # Refresh inventory

    inventory_map = getInventory()
    inventory_beers = {}

    for c in beerCategories:
        for i in inventory_map[c]: 
            style, abv = '', ''
            for t in i['tags']['elements']:
                if tagAbvRE.match(t['name']):
                    abv = t['name'].split('=')[1]
                if tagStyleRE.match(t['name']):
                    style = t['name'].split('=')[1]
            if c not in inventory_beers.keys():
                inventory_beers[c] = []
            i['abv'] = abv
            i['style'] = style
            i['name'] = filterName(i['name'])
            i['price'] = filterPrice(i['price'])

            inventory_beers[c].append(i)

    inventory_wines = {}

    for c in wineCategories:
        for i in inventory_map[c]: 
            if c not in inventory_wines.keys():
                inventory_wines[c] = []
            i['name'] = filterName(i['name'])
            i['price'] = filterPrice(i['price'])
            inventory_wines[c].append(i)

    # Run against templating 

    with open('./index.html') as f:
        tmpl = Template(f.read())

    menu_page = tmpl.render(
            inventory_beers = inventory_beers,
            inventory_wines = inventory_wines,
            )

    # Upload to google-storage

    storage_client = storage.Client()

    bucket = storage_client.bucket(STORAGE_BUCKET)
    blob = bucket.blob('index.html')

    h = hashlib.md5(menu_page.encode('utf-8')).hexdigest()
    h2 = hashlib.md5(blob.download_as_string()).hexdigest()

    if h != h2:
        blob.reload()
        #blob.upload_from_string(menu_page,
        #        content_type='text/html'
        #        )

        print(
            "index.html uploaded to gs://{}".format(STORAGE_BUCKET)
        )
    else:
        print("Current index.html matches new, so not doing anything.")

    with open('/tmp/index.html', 'w') as f: 
        f.write(menu_page)

    



main()

