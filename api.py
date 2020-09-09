from bottle import route, run
import subprocess, os, json, sys, re, psycopg2

CONFIG_FILE = 'config.json'
NAME_RE     = re.compile("([!]?)c([1-6])r([1-9][0-9]?)s([1-9][0-9]?)$")

"""
Open and load a file at the json format
"""

def open_and_load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as config_file:
            return json.loads(config_file.read())
    else:
        print "File [%s] doesn't exist, aborting." % (CONFIG_FILE)
        sys.exit(1)

def connect(db):
    con = psycopg2.connect(host = config['db_host'],
                           user = config['db_user'],
                           password = config['db_pass'],
                           database = db)
    cursor = con.cursor()
    return (con, cursor)

        
def check_name(name):
    if re.match(NAME_RE, name.lower()):
        return True
    return False;

def check_mac(mac):
    if re.match("[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", mac.lower()):
        return True
    return False;


def find_subnet(net):
    con, cursor = connect("dhcp")
    cursor.execute("SELECT id FROM subnet WHERE network = '%s';" % net)
    subnet = cursor.fetchone()
    con.close()
    return subnet[0]

def find_zone(domain):
    con, cursor = connect("dns")
    cursor.execute("SELECT id FROM zone WHERE name = '%s';" % domain)
    zone = cursor.fetchone()
    con.close()
    return zone[0]

def insert_dhcp(name, mac, ip, subnet, update):
    con, cursor = connect("dhcp")
    cursor.execute("SELECT id, mac_address, ip_address FROM host WHERE  mac_address = '%s' OR ip_address = '%s';" % (mac, ip))
    res = cursor.fetchone()
    if ((update == False) and (res != None)):
        return False

    if ((update == True) and (res != None)):
        print "uuu %s update mac to %s" % (name, mac)
        q = "DELETE FROM host WHERE id = %s;" % res[0]
        cursor.execute(q)

    q = "INSERT INTO host (name, mac_address, ip_address, subnet_id) VALUES ('%s', '%s', '%s', %d);" % (name, mac, ip, subnet)
    cursor.execute(q)
    con.commit()
    con.close()
    return True
    
def insert_dns(name, ip, zone_id, name_r, ip_r, zone_r, update):
    if (update):
        return True
    con, cursor = connect("dns")
    cursor.execute("SELECT id, reverse_id, host, data FROM record WHERE  host = '%s' OR data = '%s';" % (name, ip))
    res = cursor.fetchone()
    if (res != None):
        return False
    
    q = "INSERT INTO record (host, data, type, view, zone_id) VALUES (%s, %s, 'PTR', 'Internal', %s) RETURNING id;"
    res = cursor.execute(q, (ip_r, name_r, zone_r))
    id_r = cursor.fetchone()[0]

    q = "INSERT INTO record (host, data, type, view, zone_id, reverse_id) VALUES (%s, %s, 'A', 'Internal', %s, %s);"
    res = cursor.execute(q, (name, ip, zone_id, id_r))
    
    con.commit()
    con.close()
    return True
    
def do_enroll(name, mac):
    res     = re.match(NAME_RE, name )
    update  = res.group(1) == '!'
    name    = name.replace(res.group(1), '')
    cluster = res.group(2)
    row     = res.group(3)
    pos     = res.group(4)
    ip      = "10.1%s.%s.%s" % (cluster, row, pos)
    ip_r    = "%s.%s.1%s"    % (pos, row, cluster)
    net     = "10.1%s.0.0"   % (cluster)
    
    subnet = find_subnet(net)
    zone   = find_zone(config["domain"]);
    zone_r = find_zone(config["domain_r"]);
    name_r = "%s.%s." % (name, config["domain"])
    
    if (insert_dhcp(name, mac, ip, subnet, update) == False):
        print "*** %s : %s  !!! FAILED !!!" % (name, ip)
        return '{"code":101, "message":"dhcp insert failed"}'
    
    if (insert_dns(name, ip, zone, name_r, ip_r, zone_r, update) == False):
        return '{"code":102, "message":"dns insert failed"}'

    print "--- %s : %s" % (name, ip)
    return '{"code":200,"message":"Success!"}'


@route('/')
def hello():
    return "MDS 42 API"

@route('/enroll/<name>/<mac>')
def enroll(name, mac):
    if (check_mac(mac) != True):
        return "bad mac address"
    if (check_name(name) != True):
        return "bad name"
    return do_enroll(name, mac)

if __name__ == "__main__":
    config = open_and_load_config()
    try:
        run(host=config["host"], port=config["port"], debug=config["debug"], quiet=config["quiet"])
    except Exception as e:
        print e
