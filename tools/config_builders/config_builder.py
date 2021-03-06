#!/usr/bin/python3
#
# Copyright 2017 SIDN
# Written by Jelte Jansen
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


#
# This is the full builder
# We'll probably split up the server-specific builders later
#
# In general, the final output should contain 3 elements:
# - A config file (may be None, or an input file)
# - A set of commands to update or re-read said file
# 

# The main output dir is
# output/servers
# That dir will contain subdirs per server (nsd, bind9, knot, etc.)
# By convention, the 'config file' will be called
# output/servers/<servername>/<servername>.conf
# and the update 'script' will be
# output/servers/<servername>/update.sh

from workbench import env, zonedata, dnsutil
import optparse
import os

CONFIG_BASE_PATH = env.OUTPUT_BASE_PATH + "/servers"

# TODO: separate servers, make auto-modules?

class TSIGKey():
    def __init__(self, name, algorithm, secret):
        self.name = name
        self.algorithm = algorithm
        self.secret = secret
    
    def get_name(self):
        return self.name
    
    def get_algorithm(self):
        return self.algorithm
    
    def get_secret(self):
        return self.secret

"""
Some servers want slightly different names for some values than others
"""
def get_tsig_full_algo_name(algo):
    if algo == "hmac-md5":
        return "HMAC-MD5.SIG-ALG.REG.INT"
    else:
        return algo

gtsig_keys = [
    TSIGKey("wb_md5", "hmac-md5", "Wu/utSasZUkoeCNku152Zw=="),
    TSIGKey("wb_sha1", "hmac-sha1", "Vn37JPSCmaCHKJhghcpRg8m6PlQ="),
    TSIGKey("wb_sha1_longkey", "hmac-sha1",
            "uhMpEhPq/RAD9Bt4mqhfmi+7ZdKmjLQb/lcrqYPXR4s/nnbsqw=="),
    TSIGKey("wb_sha256", "hmac-sha256",
            "npfrIJjt/MJOjGJoBNZtsjftKMhkSpIYMv2RzRZt1f8=")
]


class ConfigGenerator:
    def __init__(self, zds):
        self.zds = zds
        self.tsig_keys = gtsig_keys

    def create_config_file(self):
        raise Exception("NotImplementedYet (fixme)")
    
    def create_update_script(self):
        raise Exception("NotImplementedYet (fixme)")
    
    def get_name(self):
        raise Exception("NotImplementedYet (fixme)")
    
    def get_start(self):
        raise Exception("NotImplementedYet (fixme)")
    
    def get_end(self):
        raise Exception("NotImplementedYet (fixme)")

    def get_tsig_key_chunk(self, tsig_key):
        raise Exception("NotImplementedYet (fixme)")

    def get_config_filename(self):
        return "%s/%s/%s.conf" % (CONFIG_BASE_PATH,
                                  self.get_name(),
                                  self.get_name())
    
    def create_config_file(self):
        os.makedirs(os.path.dirname(self.get_config_filename()), exist_ok=True)
        with open(self.get_config_filename(), "w") as cf_out:
            for line in self.get_start():
                cf_out.write(line)
                cf_out.write("\n")

            for tsig_key in self.tsig_keys:
                for line in self.get_tsig_key_chunk(tsig_key):
                    cf_out.write(line)
                    cf_out.write("\n")

            for zd in self.zds:
                if self.is_primary_for(zd) or self.is_secondary_for(zd):
                    for line in self.get_zone_chunk(zd):
                        cf_out.write(line)
                        cf_out.write("\n")
                
            for line in self.get_end():
                cf_out.write(line)
                cf_out.write("\n")

    def get_update_script_filename(self):
        return "%s/%s/update.sh" % (CONFIG_BASE_PATH, self.get_name())
    
    def create_update_script(self):
        with open(self.get_update_script_filename(), "w") as uf_out:
            for line in self.get_update_lines():
                uf_out.write(line)
                uf_out.write("\n")

    def is_primary_for(self, zd):
        master_names = zd.get("primary_names")
        return master_names is not None and (master_names == [] or self.get_name() in master_names)

    def is_secondary_for(self, zd):
        return self.get_name() in zd.get("secondary_names")
    
def get_primary_addr(zd):
    k = zd.get("primary_names")[0]
    if k in env.SERVERS:
        return env.SERVERS[k]
    else:
        return k

class NSDConfigGenerator(ConfigGenerator):

    def get_name(self):
        return "nsd"
    
    def get_start(self):
        return [
            "# NSD(3) Config file",
            "# as created by the Workbench Generator tool",
            "",
            ""
        ]

    def get_end(self):
        return []
    
    def get_tsig_key_chunk(self, key):
        lines = [ "key:" ]
        lines.append("\tname: \"%s\"" % key.get_name())
        lines.append("\talgorithm: %s" % key.get_algorithm())
        lines.append("\tsecret: \"%s\"" % key.get_secret())
        lines.append("")
        return lines
    
    def get_zone_chunk(self, zd):
        zname = zd.get("name")
        zname_u = dnsutil.ufqdn(zname)

        lines = [ "zone:" ]
        lines.append("\tname: \"%s\"" % zname_u)
        lines.append("\tzonefile: \"/var/workbench/zones/%s\"" % zname_u)
        
        # Allow all types of transfers from the entire world
        lines.append("\tprovide-xfr: 0.0.0.0/0 NOKEY")
        lines.append("\tprovide-xfr: ::0/0 NOKEY")
        for tk in self.tsig_keys:
            lines.append("\tprovide-xfr: 0.0.0.0/0 %s" % tk.get_name())
            lines.append("\tprovide-xfr: ::0/0 %s" % tk.get_name())
        lines.append("")

        if self.is_primary_for(zd):
            for sec in zd.get("secondary_names"):
                lines.append("\tnotify: %s NOKEY" % env.SERVERS[sec])
        elif self.is_secondary_for(zd):
                master_addr = get_primary_addr(zd)
                lines.append("\tallow-notify: %s NOKEY" % (master_addr))
                lines.append("\trequest-xfr: %s NOKEY" % (master_addr))
        return lines
    
    def get_update_lines(self):
        # Note: the script called here must be present
        # (it is not a standard reload script)
        # No loger used in 2019 version
        return [
            "sudo /etc/nsd3/nsdc_update"
        ]

class NSD4ConfigGenerator(ConfigGenerator):

    def get_name(self):
        return "nsd4"
    
    def get_start(self):
        return [
            "# NSD 4 Config file",
            "# as created by the Workbench Generator tool",
            "",
            "server:",
            "       #ip-address: 127.0.0.1@5333",
            "       ip-address: 94.198.159.33",
            "       ip-address: 2a00:d78:0:712:94:198:159:33",
            "       zonesdir: \"/var/dns-workbench/zones\"",
            "       identity: \"nsd4.sidnlabs.nl\"",
            "       nsid: \"ascii_nsd4.sidnlabs.nl\"",
            "       #logfile: \"/var/log/nsd.log\"",
            "",
            "remote-control:",
            "        control-enable: yes",
            "        server-cert-file: \"/etc/nsd/nsd_server.pem\"",
            "        control-cert-file: \"/etc/nsd/nsd_control.pem\"",
            ""
        ]

    def get_end(self):
        return []
    
    def get_tsig_key_chunk(self, key):
        lines = [ "key:" ]
        lines.append("\tname: \"%s\"" % key.get_name())
        lines.append("\talgorithm: %s" % key.get_algorithm())
        lines.append("\tsecret: \"%s\"" % key.get_secret())
        lines.append("")
        return lines
    
    def get_zone_chunk(self, zd):
        zname = zd.get("name")
        zname_u = dnsutil.ufqdn(zname)

        lines = [ "zone:" ]
        lines.append("\tname: \"%s\"" % zname_u)
        # check zonesdir: in the server: section
        lines.append("\tzonefile: \"%s\"" % zname_u)
        
        # Allow all types of transfers from the entire world
        lines.append("\tprovide-xfr: 0.0.0.0/0 NOKEY")
        lines.append("\tprovide-xfr: ::0/0 NOKEY")
        for tk in self.tsig_keys:
            lines.append("\tprovide-xfr: 0.0.0.0/0 %s" % tk.get_name())
            lines.append("\tprovide-xfr: ::0/0 %s" % tk.get_name())

        if self.is_primary_for(zd):
            for sec in zd.get("secondary_names"):
                lines.append("\tnotify: %s NOKEY" % env.SERVERS[sec])
        elif self.is_secondary_for(zd):
                master_addr = get_primary_addr(zd)
                lines.append("\tallow-notify: %s NOKEY" % (master_addr))
                lines.append("\trequest-xfr: %s NOKEY" % (master_addr))
        return lines

    # NSD4
    def get_update_lines(self):
        return [
            "#/usr/sbin/nsd-control reload",
            "systemctl stop nsd",
            "rm -rf /var/lib/nsd/*",
            "systemctl start nsd"
        ]

class Bind9ConfigGenerator(ConfigGenerator):
    # Note: the current setup includes this file, so other config
    # is already present on the system.
    def get_name(self):
        return "bind9"
    
    def get_start(self):
    # TODO: include the currently seperate named.conf.options part here
        return [
                "// BIND 9 config for the SIDN workbench",
                "// Generated by the config builder tool",
                "",
                ""
        ]

    def get_end(self):
        return [
        ]
    
    def get_tsig_key_chunk(self, key):
        lines = [
            "key \"%s\" {" % key.get_name(),
            "        algorithm %s;" % key.get_algorithm(),
            "        secret \"%s\";" % key.get_secret(),
            "};",
            ""
        ]
        return lines
    
    def get_zone_chunk(self, zd):
        zname = zd.get("name")
        zname_u = dnsutil.ufqdn(zname)

        lines = [
            "zone \"%s\" {" % zname,
            "        file \"/var/dns-workbench/zones/%s\";" % zname_u
        ]
        
        if self.is_primary_for(zd):
            lines.append("        type master;")
            secondary_addrs = [env.SERVERS[n] for n in zd.get("secondary_names")]
            if len(secondary_addrs) > 0:
                lines.append("        also-notify { %s; };" % "; ".join(secondary_addrs))
        elif self.is_secondary_for(zd):
            lines.append("        type slave;")
            lines.append("        masters { %s; };" % get_primary_addr(zd))

        lines.extend([
            "};"
        ])
        return lines
    
    # BIND9
    def get_update_lines(self):
        return [
            "#rndc reconfig",
            "#rndc reload",
            "systemctl restart bind9"
        ]

class Bind10ConfigGenerator(ConfigGenerator):
    def get_name(self):
        return "bind10"
    
    def get_start(self):
        return [
            "config set tsig_keys/keys []",
            "config set Zonemgr/secondary_zones []",
            "config set Xfrin/zones []",
            "config set Xfrout/zone_config []",
            ""
        ]

    def get_end(self):
        return [
            "config commit"
        ]
    
    def get_tsig_key_chunk(self, key):
        lines = [
            "config add tsig_keys/keys \"%s:%s:%s\"" % 
            (key.get_name(), key.get_secret(),
             get_tsig_full_algo_name(key.get_algorithm()))
        ]
        return lines
    
    def get_zone_chunk(self, zd):
        # Note: the actual zones themselves are loaded with the update script
        # this merely sets them up for transfer-out
        xfrout_acl_base = "{ \"action\": \"ACCEPT\" }"
        xfrout_acl_base_key = "{ \"action\": \"ACCEPT\", \"key\": \"%s\" }"
        xfrout_acl = " [ "
        xfrout_acl += ", ".join([ xfrout_acl_base_key % (key.get_name())
                                  for key in self.tsig_keys
                                ])
        xfrout_acl += ", "  + xfrout_acl_base + " ] "

        zname = zd.get("name")
        zname_u = dnsutil.ufqdn(zname)

        lines = []
        if self.is_secondary_for(zd):
            lines.append(
                "config add Xfrin/zones { " +
                    "\"name\": \"%s\"," % zname +
                    "\"class\": \"IN\"," +
                    "\"master_addr\": \"%s\"," % get_primary_addr(zd) +
                    "\"master_port\": 53" +
                " } ")
        lines.append(
            "config add Xfrout/zone_config {" +
              "\"origin\": \"%s\", " % zd.get("name") +
              "\"class\": \"IN\", " +
              "\"transfer_acl\": %s" % xfrout_acl +
            " } "
        )

        return lines
    
    # BIND10
    # No longer in use in 2019 version
    def get_update_lines(self):
        lines = []
        lines.append("cat /var/workbench/bind10_commands.txt | bindctl")
        for zd in self.zds:
            zname = zd.get("name")
            zname_u = dnsutil.ufqdn(zname)
            if self.is_primary_for(zd):
                lines.append("b10-loadzone %s /var/workbench/zones/%s" % (zname, zname_u))
            elif self.is_secondary_for(zd):
                lines.append("echo \"Xfrin retransfer %s\"" % (zname))
        return lines

class KnotConfigGenerator(ConfigGenerator):
    def get_name(self):
        return "knot"
    
    def get_start(self):
        # TODO: Add the IPv6 addresses as well?
        return [ "server:",
                 "  identity: knot.sidnlabs.nl",
                 "  nsid: knot.sidnlabs.nl",
                 "  #listen: 127.0.0.1",
                 "  listen: 94.198.159.27",
                 "  #listen: 127.0.0.1@5327",
                 "  #listen: ::1",
                 "  listen: 2a00:d78:0:712:94:198:159:27",
                 "  # User for running the server.",
                 "  user: knot:knot",
                 "",
                 "remote:",
                 "  # PowerDNS:",
                 "  - id: m94.198.159.26",
                 "    address: 94.198.159.26",
                 "  # Knot:",
                 "  - id: m94.198.159.27",
                 "    address: 94.198.159.27",
                 "  # Yadifa:",
                 "  - id: m94.198.159.28",
                 "    address: 94.198.159.28",                 
                 "  # NSD4:",
                 "  - id: m94.198.159.33",
                 "    address: 94.198.159.33",
                 "  # BIND9:",
                 "  - id: m94.198.159.39",
                 "    address: 94.198.159.39",
                 "",
                 "log:",
                 "  - target: syslog",
                 "    server: notice",
                 "    zone: notice",
                 "    any: notice",
                 "key:",
                 "  - id: wb_md5",
                 "    algorithm: hmac-md5",
                 "    secret: Wu/utSasZUkoeCNku152Zw==",
                 "  - id: wb_sha1",
                 "    algorithm: hmac-sha1",
                 "    secret: Vn37JPSCmaCHKJhghcpRg8m6PlQ=",
                 "  - id: wb_sha1_longkey",
                 "    algorithm: hmac-sha1",
                 "    secret: uhMpEhPq/RAD9Bt4mqhfmi+7ZdKmjLQb/lcrqYPXR4s/nnbsqw==",
                 "  - id: wb_sha256",
                 "    algorithm: hmac-sha256",
                 "    secret: npfrIJjt/MJOjGJoBNZtsjftKMhkSpIYMv2RzRZt1f8=",
                 "acl:",
                 "  - id: any",
                 "    action: transfer",
                 "  - id: awb_md5",
                 "    key: wb_md5",
                 "    action: transfer",
                 "  - id: awb_sha1",
                 "    key: wb_sha1",
                 "    action: transfer",
                 "  - id: awb_sha1_longkey",
                 "    key: wb_sha1_longkey",
                 "    action: transfer",
                 "  - id: awb_sha256",
                 "    key: wb_sha256",
                 "    action: transfer",
                 "",
                 "zone:" ]

    def get_end(self):
        return [ "",
                 "" ]
    
    def get_tsig_key_chunk(self, key):
        # TODO
        lines = [ ]
        return lines
    
    def get_zone_chunk(self, zd):
        zname = zd.get("name")
        zname_u = dnsutil.ufqdn(zname)

        lines = [
            "  - domain: %s" % zname,
            # TODO: tsig
            "    acl: any",
            "    acl: awb_md5",
            "    acl: awb_sha1",
            "    acl: awb_sha1_longkey",
            "    acl: awb_sha256",
        ]
        
        if self.is_primary_for(zd):
            lines.append("    file: \"/var/dns-workbench/zones/%s\"" % zname_u)
            for secondary in zd.get("secondary_names"):
                raise Exception("NotImplYet " + self.get_name() + " " + zd.get("name"))
        elif self.is_secondary_for(zd):
            primary_addr = get_primary_addr(zd)
            lines.append("    master: m%s" % primary_addr)
            #lines.append("    notify-in m%s;" % primary_addr)
        
        lines.extend([
            ""
        ])

        return lines
    
    # Knot
    def get_update_lines(self):
        # Note: this calls a custom script which was created manually
        return [
            # "sudo /etc/knot/knotc_update"
            "#/usr/sbin/knotc -s /var/run/knot/knot.sock reload",
            "systemctl stop knot",
            "rm -rf /var/lib/knot/*",
            "systemctl start knot"
        ]

class PowerDNSConfigGenerator(ConfigGenerator):
    # Note: similar to bind10, we have a 'static' config and
    # manipulate the zone data through the database.
    # Part of that is done through the custom script
    # /var/workbench/add_or_update_zone
    #
    # 2019 version update: 
    # We are a simpel superslave, so the above does no longer apply
    #

    def get_name(self):
        return "powerdns"
    
    def get_start(self):
        return [
            "# PowerDNS Config file for BIND backend",
            "# as created by the Workbench Generator tool",
            ""
        ]

    def get_end(self):
        return [
        ]
    
    def get_tsig_key_chunk(self, key):
        # TODO: TSIG done by hand for now (well actually... not even that, but might do - see Knot as example)
        lines = [
        ]
        return lines
    
    def get_zone_chunk(self, zd):
        # We load most files with the bind backend, except for apexcname.wb.sidnlabs.nl, which we zone2sql into sqlite3 backend
        # because of https://github.com/PowerDNS/pdns/issues/7437
        # Copied thie part mostly from Bind9ConfigGenerator
        zname = zd.get("name")
        zname_u = dnsutil.ufqdn(zname)

        lines = [
            "zone \"%s\" {" % zname,
            "        file \"/var/dns-workbench/zones/%s\";" % zname_u
        ]
        
        if self.is_primary_for(zd):
            lines.append("        type native;")
            # Secondory stuff left out here - won't use it anyway

        # again a dirty trick... zone2sql stripped the DNSSEC so that method couldn't be used
        lines.extend([
            "};",
            "zone \"apexcname.wb.sidnlabs.nl.\" {",
            "        file \"/var/dns-workbench/zones/apexcname.wb.sidnlabs.nl\";",
            "        type native;",
            "};"
        ])
        return lines

    # PowerDNS 2019 version
    # Maybe too strong?
    def get_update_lines(self):
        return [
            "systemctl stop pdns",
            "echo 'empty the entire database'",
            "sqlite3 /var/lib/powerdns/pdns.sqlite3 < /etc/powerdns/powerdns_clean.sql",
            "rm /var/lib/powerdns/bind-dns-db.sqlite3",
            "pdnsutil create-bind-db /var/lib/powerdns/bind-dns-db.sqlite3",
            "chown pdns:pdns /var/lib/powerdns/bind-dns-db.sqlite3",
            "for a in $(pdnsutil list-all-zones native); do pdnsutil set-presigned $a; done",
            "# That nasty types[-signed].wb.sidn.nl zone has to be slaved by sqlite3, so yet another exception:",
            "# This also includes nsec3-opt-out and wildcards-nsec3 zones btw",
            "echo 'slaving types[-signed] and nsec3-opt-out and wildcards-nsec3 from bind9'",
            "sqlite3 /var/lib/powerdns/pdns.sqlite3 < /etc/powerdns/powerdns_slaves.sql",
            "# TODO: ANALYZE; ?",
            "systemctl start pdns",
        ]
    # Former version    
    #def get_update_lines(self):
    #    lines = []
    #    for zd in self.zds:
    #        zname = zd.get("name")
    #        zname_u = dnsutil.ufqdn(zname)
    #        if self.is_primary_for(zd):
    #            # zone in database goes
    #            lines.append("sudo /var/workbench/add_or_update_zone.sh %s %s" % (zname_u, "zones/%s" % zname_u))
    #            # if it is slave, it should work automagically (supermasters)
    #        
    #        # dnssec stuff goes for both
    #        lines.append("sudo /var/workbench/pdnssec_set.sh %s" % zname_u)
    #
    #    return lines

class EmptyConfigGenerator(ConfigGenerator):
    def get_name(self):
        return ""
    
    def get_start(self):
        return [
            ""
        ]

    def get_end(self):
        return []
    
    def get_tsig_key_chunk(self, key):
        lines = [ ]
        return lines
    
    def get_zone_chunk(self, zd):
        zname = zd.get("name")
        zname_u = dnsutil.ufqdn(zname)

        lines = [ ]
        return lines
    
    def get_update_lines(self):
        return [
            ""
        ]


class YadifaConfigGenerator(ConfigGenerator):
    def get_name(self):
        return "yadifa"
    
    def get_start(self):
    # TODO: include (at least some of) the stuff from /etc/yadifa/yadifad.conf here
        return [
            # We use the (adapted) default from the Ubuntu-package and only include the zone-sections
            "# This file is automatically generated (by create_configs.sh) for the SIDN Labs DNS workbench",
            "# It should be included in the existing /etc/yadifa/yadifad.conf from the Ubuntu package",
            "",
            "# DNS workbench zone section",
            "# ==========================",
            "",
        ]

    def get_end(self):
        return [ ]
    
    def get_tsig_key_chunk(self, key):
        # TODO
        lines = [ ]
        return lines
    
    def get_zone_chunk(self, zd):
        zname = zd.get("name")
        zname_u = dnsutil.ufqdn(zname)

        lines = [
            "<zone>",
            "        domain %s" % zname,
        ]
        
        if self.is_primary_for(zd):
            lines.append("        file masters/workbench/%s" % zname_u)
            lines.append("        type master")
            # TODO for some reasons this exception is triggered and causes problems - figure out why, fix them
            # For now, just skip it, because is seems to work if we do.
            #for secondary in zd.get("secondary_names"):
            #    raise Exception("NotImplYet")            
            lines.append("        maintain-dnssec false")
            lines.append("        dnssec-mode	  off")
            lines.append("        notify-auto     false")
        elif self.is_secondary_for(zd):
            lines.append("        file slaves/workbench/%s" % zname_u)
            lines.append("        type slave")
            primary_addr = get_primary_addr(zd)
            lines.append("        master %s port 53" % primary_addr)
        
        lines.append("</zone>")
        lines.append("")
        return lines
    
    def get_update_lines(self):
        return [
            # Note: this calls a custom script which was created manually
            # "sudo /var/workbench/restart_yadifa.sh"
            # 2019 version:
            "systemctl stop yadifa",
            "rm -rf /var/lib/yadifa/xfr/*",
            "systemctl start yadifa",
        ]

def create_config_files_and_scripts():
    zds = dnsutil.read_all_db_files()
    generators = [
        #NSDConfigGenerator(zds),
        NSD4ConfigGenerator(zds),
        Bind9ConfigGenerator(zds),
        #Bind10ConfigGenerator(zds),
        KnotConfigGenerator(zds),
        PowerDNSConfigGenerator(zds),
        YadifaConfigGenerator(zds),
    ]
    for generator in generators:
        generator.create_config_file()
        generator.create_update_script()


if __name__=="__main__":
    parser = optparse.OptionParser()
    parser.add_option("-r", action="store_true", dest="regen",
                      help="Regenerate all files")
    (options, args) = parser.parse_args()
    create_config_files_and_scripts()
