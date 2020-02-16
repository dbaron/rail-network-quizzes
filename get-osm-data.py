#!/usr/bin/env python3
# vim: set fileencoding=UTF-8

import imp
import sys
import copy
import re
import os.path
import itertools
import json
from optparse import OptionParser

sys.path.append("/home/dbaron/builds/openstreetmap/osmapi")
import osmapi

passwords = imp.load_source("passwords", "/home/dbaron/.passwords.py")

op = OptionParser()
(options, args) = op.parse_args()

if len(args) != 1:
    op.error("expected 1 argument but got {0}".format(len(args)))
network_relation_id = None
try:
    network_relation_id = int(args[0])
except:
    op.error("expected a single integer argument but got \"{0}\"".format(args[0]))

api = osmapi.OsmApi(username=passwords.get_osm_username(), password=passwords.get_osm_password())

metro_line_relations = []
network_relation = api.RelationGet(network_relation_id)
network_name = network_relation[u"tag"][u"name"]
for nitem in network_relation[u"member"]:
    if nitem[u"type"] == u"relation":
        rel_id = nitem[u"ref"]
        metro_line_relations.append(rel_id)

lines = []
station_node_ids = set()
ways_to_fetch = set()

for master_rel_id in metro_line_relations:
    route_master_relation = api.RelationGet(master_rel_id)
    line = {}
    lines.append(line)
    ways_and_counts = dict()
    line_stations_set = set()
    line_stations_list = []
    line["ways"] = ways_and_counts
    line["stops"] = line_stations_list
    mtags = route_master_relation[u"tag"]
    line["name"] = mtags[u"name"]
    line["ref"] = mtags[u"ref"]
    if (u"colour" in mtags):
        line["color"] = mtags[u"colour"]
    for mitem in route_master_relation[u"member"]:
        if mitem[u"type"] == u"relation":
            rel_id = mitem[u"ref"]
            route_relation = api.RelationGet(rel_id)
            rtags = route_relation[u"tag"]
            if (u"colour" in rtags):
                if ("color" in line) and line["color"] != rtags[u"colour"]:
                    sys.stderr.write("WARNING: relation {} has mismatching color\n".format(rel_id))
                line["color"] = rtags[u"colour"]
            for ritem in route_relation[u"member"]:
                ritem_ref = ritem[u"ref"]
                if ritem[u"type"] == u"node" and (ritem[u"role"] == u"stop" or ritem[u"role"] == u"stop_entry_only" or ritem[u"role"] == u"stop_exit_only"):
                    station_node_ids.add(ritem_ref)
                    if not (ritem_ref in line_stations_set):
                        line_stations_set.add(ritem_ref)
                        line_stations_list += [ritem_ref]
                elif ritem[u"type"] == u"way" and (ritem[u"role"] == u"" or ritem[u"role"] == u"forward" or ritem[u"role"] == u"backward"):
                    # On a few lines, split parts are tagged as deprecated "forward"
                    ways_and_counts[ritem_ref] = ways_and_counts.get(ritem_ref, 0) + 1
                    ways_to_fetch.add(ritem_ref)
                elif ritem[u"type"] == u"way" and (ritem[u"role"] == u"platform" or ritem[u"role"] == u"platform_entry_only" or ritem[u"role"] == u"platform_exit_only" or ritem[u"role"] == u"access"):
                    pass
                elif ritem[u"type"] == u"relation" and ritem[u"role"] == u"platform":
                    pass
                else:
                    sys.stderr.write("WARNING: relation {} has unexpected member type {} role {} ref {}\n".format(rel_id, ritem[u"type"], ritem[u"role"], ritem_ref))

# somewhat based on grouper() in https://docs.python.org/2/library/itertools.html
def grouper(iterable, n):
    args = [iter(iterable)] * n
    return map(lambda tup: [item for item in tup if item is not None],
               itertools.zip_longest(fillvalue=None, *args))

ways = dict()
for ways_group in grouper(ways_to_fetch, 20):
    ways.update(api.WaysGet(ways_group))

nodes_to_fetch = set(station_node_ids)
for way in ways.values():
    nodes_to_fetch.update(way[u"nd"])

nodes = dict()
for nodes_group in grouper(nodes_to_fetch, 100):
    nodes.update(api.NodesGet(nodes_group))

for way in ways.values():
    del way["timestamp"]
    del way["changeset"]
    del way["user"]
    del way["uid"]
    if not way["visible"]:
        sys.stderr.write("WARNING: way {} is not visible!\n".format(way["id"]))
    del way["visible"]

for node in nodes.values():
    del node["timestamp"]
    del node["changeset"]
    del node["user"]
    del node["uid"]
    if not node["visible"]:
        sys.stderr.write("WARNING: node {} is not visible!\n".format(node["id"]))
    del node["visible"]

data = { "network_relation_id": network_relation_id, "network_name": network_name,
         "lines": lines, "ways": ways, "nodes": nodes }
outfile = open("{0}-data.json".format(network_relation_id), "w")
json.dump(data, outfile, indent=True, sort_keys=True)
outfile.close()
