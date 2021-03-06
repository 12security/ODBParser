import os
from elasticsearch import Elasticsearch, exceptions
import json
from colorama import Fore
import ODBconfig
from ODBlib.ODBhelperfuncs import updatestatsfile
from elasticsearch1 import Elasticsearch as es1


basepath = ODBconfig.basepath
if not basepath:
    basepath = os.path.join(os.getcwd(),"open directory dumps")

if not os.path.exists(basepath):
    os.makedirs(basepath)
#to do: split json file once gets to 10gb? or maybe not, dunno

def newESdump(ipaddress,indexname,out_dir, portnumber=9200,size=1000,properjson=False):

    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    os.chdir(out_dir)
    es = Elasticsearch([{'host': ipaddress, 'port': portnumber, "timeout": 1000, "requestTimeout": 1000,'retry_on_timeout':True,'max_retries':50}]) #decrease timeout if you like, but good to have up there esp for really big files and if scroll size is at 10000
    dump_fname = f'{ipaddress}_{indexname}_ES_mapping.json'
    # print(F'Dumping index \033[94m{index_name}\x1b[0m in file at \033[94m{dump_fname}\x1b[0m')
    ESversion = int(es.info()["version"]["number"].rsplit(".")[0]) #check version
    if ESversion <2: #check if less than v2 when scrolling changed
        es = es1([{'host': ipaddress, 'port': portnumber, "timeout": 1000, "requestTimeout": 1000,
                             'retry_on_timeout': True,
                             'max_retries': 100}])  # decrease timeout if you like, but good to have up there esp for really big files and if scroll size is at 10000

    index_info = es.indices.get(indexname) #get mapping
    #print(f"        Got mapping for {Fore.LIGHTRED_EX}{indexname}{Fore.RESET}")
    with open(os.path.join(out_dir,dump_fname), 'w') as dump_fd:
        dump_fd.write(json.dumps(index_info, indent=4))

    hits = []
    try:

        results = es.search(index=indexname,scroll="1m",size=size) #add from parameter to offset
        #print("search page 1")
        sid = results['_scroll_id']
        scroll_size = len(results['hits']['hits'])

        totalhits = results['hits']['total']
        if type(totalhits) ==dict: #ES changed this field in recent update
            totalhits = totalhits["value"]
        totalpages = totalhits/size
        #scrollhits = len(results['hits']['hits'])
        print(f"    Dumping {Fore.LIGHTBLUE_EX}{totalhits:,d}{Fore.RESET} records from {Fore.LIGHTRED_EX}{indexname}{Fore.RESET} in batches of {Fore.LIGHTBLUE_EX}{size:,d}{Fore.RESET} (about {Fore.LIGHTBLUE_EX}{round(totalpages):,d}{Fore.RESET} total pages).")
        for x in results['hits']['hits']:
            hits.append(x["_source"])
        count = 1
        filecount =0
        with open(os.path.join(out_dir, f"{ipaddress}_{indexname}_ES.json"), "w",encoding="utf8") as f:
            if properjson:
                json.dump(hits,f)
            else:
                for y in hits:
                    f.write(json.dumps(y)+"\n")
        updatestatsfile(1, len(hits), 1, type="ElasticSearch")

        if scroll_size < totalhits:#was getting scroll error when trying to get hits on page 2 if no page 2, so fuck it wrote this condition
            while scroll_size > 0:
                try:
                    hits=[] #reset hits
                    count +=1
                    filecount +=1
                    results = es.scroll(scroll_id=sid, scroll='1m')
                    # Update the scroll ID
                    sid = results['_scroll_id']

                    scroll_size = len(results['hits']['hits'])

                    for x in results['hits']['hits']:
                        hits.append(x["_source"])
                    if hits:
                        print(F"        Dumping results from page {Fore.LIGHTBLUE_EX}{str(count)}{Fore.RESET}", end="\r")

                        with open(os.path.join(out_dir,f"{ipaddress}_{indexname}_ES.json"), "ab+") as newZ: #so dont have to store whole json in memory

                            if properjson:
                                newZ.seek(-1, 2)
                                newZ.truncate()
                                newZ.write(",".encode())
                                for y in hits[:-1]:
                                    newZ.write(json.dumps(y).encode())
                                    newZ.write(",".encode())
                                newZ.write(json.dumps(hits[-1]).encode())
                                newZ.write(']'.encode())
                            else:
                                for y in hits:
                                    newZ.write(json.dumps(y).encode()+b"\n")

                        updatestatsfile(0, len(hits), 0, type="ElasticSearch")

                except Exception as e:
                    scroll_size = 0
                    with open(os.path.join(basepath, "EsErrors.txt"), 'a') as outfile:
                        outfile.write(f"{ipaddress}:{indexname}-failed on page {str(count)} because {str(e)}\n")
                    if "ConnectionTimeout" in str(e): #i know, i know, just got lazy
                        reason = f" due to connection timeout"
                    elif "Failed to decode scrollId" in str(e):
                        reason = "Scrolling not supported on this version of ES db with this version of Python client"
                    else:
                        reason=""
                    print (F"        failed on page {str(count)}: {reason} (check logs for more info)") #need to add extra error handling
                    #break
    except exceptions.ConnectionError:
        print(F"    Couldn't connect to {Fore.LIGHTRED_EX}{indexname}{Fore.RESET} after 3 tries")




#example
#dump_index("http://138.68.48.172:9200/users","testing",batch=10000)