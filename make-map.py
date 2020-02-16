#!/usr/bin/env python3

# Copyright 2020 L. David Baron
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os.path
import math
import itertools
import re
import unicodedata
from optparse import OptionParser

op = OptionParser()
(options, args) = op.parse_args()

if len(args) != 1:
    op.error("expected 1 argument but got {0}".format(len(args)))
network_relation_id = None
try:
    network_relation_id = int(args[0])
except:
    op.error("expected a single integer argument but got \"{0}\"".format(args[0]))

# Read in the data saved by "get-osm-data.py", from OpenStreetMap.
io = open(os.path.join(os.path.dirname(__file__), "{0}-data.json".format(network_relation_id)))
data = json.load(io)
io.close()

lines = data["lines"]
ways = data["ways"]
nodes = data["nodes"]
network_name = data["network_name"]
stops_by_name = dict()
stops_by_id = dict()

def line_to_name(line):
    return line["ref"]

def station_name_to_id(name):
    return "".join(filter(lambda c: c.isalpha(), unicodedata.normalize("NFKD", name))).lower()

# Find the bounding box of the nodes, and how we'll map those into
# coordinates in the SVG we make.
min_lat = 90
max_lat = -90
min_lon = 180
max_lon = -180
for node in nodes.values():
    lat = node["lat"]
    lon = node["lon"]
    min_lat = min(min_lat, lat)
    max_lat = max(max_lat, lat)
    min_lon = min(min_lon, lon)
    max_lon = max(max_lon, lon)

  # Approximate ratio of the distance of moving a degree of longitude to
  # a degree of latitude.  (1.002 is between the ratio of earth's
  # equatorial radius to polar radius, and the ratio of the equatorial
  # circumference to polar circumference, since this is all close enough
  # and I don't want to think it through.)
length_ratio = math.cos(math.pi * (min_lat + max_lat) / 360) * 1.002

lat_size = max_lat - min_lat
lon_size = (max_lon - min_lon) * length_ratio

# jetpunk maximum is 830 width and 600 height, but I add 30 height and 10 width
scale = min(570 / lat_size, 820 / lon_size)

def lon_to_svg(lon):
    return (lon - min_lon) * length_ratio * scale

def lat_to_svg(lat):
    return (max_lat - lat) * scale

viewBoxPadding = 5
bottomPadding = 20
width = lon_to_svg(max_lon) + 2 * viewBoxPadding
height = lat_to_svg(min_lat) + 2 * viewBoxPadding + bottomPadding
viewBox = "{} {} {} {}".format(-viewBoxPadding, -viewBoxPadding, width, height)

# Process the lines of the map
for line in lines:
    print("Processing line {}.".format(line["name"]))
    line_ways = line["ways"]

    # Build the maximal sequences of ways that don't involve any
    # forking/branching on this line.
    way_sequences = []
    ways_remaining = set(line_ways.keys())
    while len(ways_remaining) > 0:
        # We'll only go through this loop more than once if there are
        # disconnected segments of this subway line, which really
        # shouldn't happen.

        # Build a map from way endpoints back to ways, to use to join the ways
        # back together.
        way_endpoint_map = dict()
        for way_id in ways_remaining:
            way = ways[way_id]
            way_nodes = way["nd"]
            for endnode in (way_nodes[0], way_nodes[-1]):
                way_endpoint_map[endnode] = way_endpoint_map.get(endnode, []) + [way_id]

        # Sort by id so map generation is deterministic.  (They're
        # strings, but that's fine, the determinism is what matters.)
        for endpoint_map_value in way_endpoint_map.values():
            endpoint_map_value.sort()

        # Start at the first point we find in our map with a number
        # other than 2 ways.  But make it the first by _ID_ so that we
        # deterministically generate the same map each time rather than
        # relying on hash enumeration order.
        start_node = None
        start_node_fallback = None
        for (endnode, endnode_ways) in way_endpoint_map.items():
            if start_node_fallback is None or endnode < start_node_fallback:
                start_node_fallback = endnode
            if len(endnode_ways) != 2:
                if start_node is None or endnode < start_node:
                    start_node = endnode
        if start_node is None:
            # We have only circles remaining.  Pick a random starting
            # point.
            start_node = start_node_fallback

        start_node_stack = [start_node]
        while len(start_node_stack) > 0:
            current_sequence = []
            way_sequences.append(current_sequence)
            current_node = start_node_stack[-1]
            endpoints = way_endpoint_map[current_node]
            while True:
                current_way_id = None
                for way_id in endpoints:
                    if way_id in ways_remaining:
                        current_way_id = way_id
                        break
                if current_way_id is None:
                    # This is possible either:
                    #  (1) the first time through the inner loop, because we
                    #      tried starting from a node from which all the ways
                    #      have already been mapped, which we should now push
                    #      off the start node stack, or
                    #  (2) because we just completed a circle.
                    if len(current_sequence) == 0:
                        start_node_stack.pop()
                        way_sequences.pop()
                    break

                current_way = ways[current_way_id]
                direction = None
                if current_way["nd"][0] == current_node:
                    direction = 1
                    current_node = current_way["nd"][-1]
                else:
                    direction = -1
                    current_node = current_way["nd"][0]
                current_sequence.append((current_way_id, direction))
                ways_remaining.remove(current_way_id)
                endpoints = way_endpoint_map[current_node]
                if len(endpoints) != 2:
                    start_node_stack.append(current_node)
                    break

    # Convert these sequences of ways to sequences of points.
    def way_sequence_to_node_sequence(way_sequence):
        seq_nodes = []
        first = True
        for (way_id, direction) in way_sequence:
            nodeiter = ways[way_id]["nd"]
            if direction == -1:
                nodeiter = reversed(nodeiter)
            if not first:
                nodeiter = itertools.islice(nodeiter, 1, None)
            seq_nodes.extend(nodeiter)
            first = False
        return seq_nodes
    node_sequences = [way_sequence_to_node_sequence(ws) for ws in way_sequences]
    def node_to_point(node_id):
        node = nodes[str(node_id)]
        return (lon_to_svg(node["lon"]), lat_to_svg(node["lat"]))
    point_sequences = [[node_to_point(node_id) for node_id in node_sequence] for node_sequence in node_sequences]

    # Merge paths (within one line, or multiple lines with the same
    # color) that are too close together into a single path.
    # FIXME: WRITE THIS (although it's not particularly important)

    # Once all lines are done, separate lines that overlap
    # FIXME: WRITE THIS (somewhat more important than the above, but
    # depends on it and would share code)

    # Serialize the lines to an SVG path
    path_string = ""
    for point_sequence in point_sequences:
        next_command = "M"
        for (x, y) in point_sequence:
            path_string += "{} {} {} ".format(next_command, x, y)
            next_command = "L"

    path_string = path_string.rstrip(" ")
    line["path"] = path_string

    stop_names = []
    for node_id in line["stops"]:
        name = nodes[str(node_id)]["tag"]["name"]
        if network_name == "M\u00e9tro de Paris":
            if name == "Réaumur Sébastopol":
                name = "Réaumur - Sébastopol"
            if name == "Saint-Denis-Université":
                name = "Saint-Denis - Université"
            name = name.replace(" (Hopital Henri Mondor)", "")
        elif network_name == "S-Bahnlinien in Berlin":
            # remove the initial "S " from most station names
            name = re.sub("^S ", "", name)
            # remove parentheticals at the end of station names
            name = re.sub(" \\([^()]*\\)$", "", name)
        if name not in stop_names:
            stop_names.append(name)

        s = stops_by_name.get(name, set())
        s.add(node_to_point(node_id))
        stops_by_name[name] = s

        station_id = station_name_to_id(name)
        if station_id in stops_by_id:
            if stops_by_id[station_id] != name:
                raise Exception('Station name disagreement for id {}: "{}" versus "{}".'.format(station_id, stops_by_id[station_id], name))
        else:
            stops_by_id[station_id] = name

    line["stop_names"] = stop_names


map_io = open(os.path.join(os.path.dirname(__file__), "{0}-map.svg".format(network_relation_id)), "w")
map_io.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="{}" width="{}" height="{}">\n'.format(viewBox, width, height))

# Draw the subway lines
for line in lines:
    map_io.write('<path id="line{}" stroke="{}" stroke-width="3" fill="none" d="{}" />\n'.format(line_to_name(line), line["color"], line["path"]))

# Draw the subway stations
for (stop_name, stop_points) in stops_by_name.items():
    # Find the average position
    # FIXME: should really draw non-circular shapes to encompass all positions!
    count = 0
    x = 0
    y = 0
    for (px, py) in stop_points:
        x = x + px
        y = y + py
        count = count + 1
    x = x / count
    y = y / count
    map_io.write('<circle id="{}" cx="{}" cy="{}" r="3" stroke="black" stroke-width="1.3" fill="white" />\n'.format(station_name_to_id(stop_name), x, y))

map_io.write('<text x="{}" y="{}" font-size="12" text-anchor="end">© OpenStreetMap contributors</text>\n'.format(lon_to_svg(max_lon) + viewBoxPadding - 1, lat_to_svg(min_lat) + viewBoxPadding + bottomPadding - 4))
map_io.write('</svg>\n')
map_io.close()

answers_io = open(os.path.join(os.path.dirname(__file__), "{0}-answers.tab".format(network_relation_id)), "w")
answers_io.write("ID\tHINT\tHINT\tANSWER\tISNAME\n")
answers_io.write("\tid\tLine\tStation\t\n")
id_counter = 0
for line in lines:
    line_name = line_to_name(line)
    if network_name != "S-Bahnlinien in Berlin":
        line_name = "Line " + line_name
    for stop_name in line["stop_names"]:
        id_counter = id_counter + 1
        answers_io.write("i{:04}\t{}\t{}\t{}\tN\n".format(id_counter, station_name_to_id(stop_name), line_name, stop_name))
answers_io.close()
