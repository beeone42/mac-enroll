from bottle import route, run
import subprocess, os, json, sys, re, psycopg2

CONFIG_FILE = 'config.json'
NAME_RE     = re.compile("c([1-3])r([1-9][0-9]?)p([1-9][0-9]?)$")

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
    print "connecting psql/%s..." % db
    con = psycopg2.connect(host = config['db_host'],
                           user = config['db_user'],
                           password = config['db_pass'],
                           database = db)
    cursor = con.cursor()
    return (con, cursor)

        
def check_name(name):
    # if re.match("^c[1-3]r[1-9][0-9]?p[1-9][0-9]?$", name.lower()):
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

def insert_dhcp(name, mac, ip, subnet):
    con, cursor = connect("dhcp")
    cursor.execute("SELECT mac_address, ip_address FROM host WHERE  mac_address = '%s' OR ip_address = '%s';" % (mac, ip))
    res = cursor.fetchone()
    if (res != None):
        print res
        print "ip/mac already exists !"
        return False
    q = "INSERT INTO host (name, mac_address, ip_address, subnet_id) VALUES ('%s', '%s', '%s', %d);" % (name, mac, ip, subnet)
    print q
    cursor.execute(q)
    con.commit()
    con.close()
    return True
    
def insert_dns(name, ip, zone_id, name_r, ip_r, zone_r):
    con, cursor = connect("dns")
    cursor.execute("SELECT host, data FROM record WHERE  host = '%s' OR data = '%s';" % (name, ip))
    res = cursor.fetchone()
    if (res != None):
        print res
        print "host/ip already exists !"
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
    res = re.match(NAME_RE, name )
    cluster = res.group(1)
    row     = res.group(2)
    pos     = res.group(3)
    ip      = "10.1%s.%s.%s" % (cluster, row, pos)
    ip_r    = "%s.%s.1%s"    % (pos, row, cluster)
    net     = "10.1%s.0.0"   % (cluster)
    
    subnet = find_subnet(net)
    zone   = find_zone(config["domain"]);
    zone_r = find_zone(config["domain_r"]);
    name_r = "%s.%s." % (name, config["domain"])
    
    if (insert_dhcp(name, mac, ip, subnet) == False):
        return "dhcp insert failed"
    if (insert_dns(name, ip, zone, name_r, ip_r, zone_r) == False):
        return "dns insert failed"
    return "ok"


@route('/')
def hello():
    return "MDS 42 API"

@route('/enroll/<name>/<mac>')
def enroll(name, mac):
    if (check_mac(mac) != True):
        return "bad mac address"
    if (check_name(name) != True):
        return "bad name"
    res = do_enroll(name, mac)
    return "%s/%s/%s" % (name, mac, res)

if __name__ == "__main__":
    config = open_and_load_config()
    print config
    try:
        run(host=config["host"], port=config["port"], debug=config["debug"])
    except Exception as e:
        print e
