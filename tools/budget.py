#!/usr/bin/python3 -tt
# -*- coding: utf-8 -*-

"""
Cleans up budget sheets converted to CSV.
"""

import re
import sys
import csv

from decimal import Decimal


def remove_junk(data):
    """
    Remove completely bogus rows that have no meaning.
    """

    output = []
    seen_orj = False

    for row in data:
        # Strip unneeded columns.
        row = row[:7]

        if len(row) < 7:
            row += [''] * (7 - len(row))

        if not seen_orj and 'ORJ' not in row[0]:
            # Skip leading rows until we get the unit id heading.
            continue

        seen_orj = True

        if sum(map(len, row[:4])) == 0:
            # Ommit lines with no values at all.
            continue

        if 'str.' in row[-1]:
            # Ommit rows with page information, they are mostly headings.
            continue

        if row[0]:
            try:
                int(row[0])
            except:
                # Exclude rows that contain non-integer unit ids, headings.
                continue

        if not row[0] and not row[1] and row[2] and not row[3] \
                and (row[-1] or row[-2] or row[-3]):
            # Exclude breakdowns as they are not coded in any way.
            continue

        output.append(row)

    return output


def merge_cont_rows(data):
    """
    Merge rows that continue the previous row.
    """

    output = []

    for row in data:
        if row[3] and not re.match(r'^(\d+\s*-|pol\s*\.)', row[3]):
            output[-1][2] = '{} {}'.format(output[-1][2], row[2].strip())
            output[-1][3] = '{} {}'.format(output[-1][3], row[3].strip())
            output[-1][-1] = '{} {}'.format(output[-1][-1], row[-1].strip())
            output[-1][-2] = '{} {}'.format(output[-1][-2], row[-2].strip())
            output[-1][-3] = '{} {}'.format(output[-1][-3], row[-3].strip())

            output[-1] = list(map(tidy, output[-1]))

        else:
            output.append(list(map(tidy, row)))

    return output


def tidy(value):
    """Clean up and strip a string field."""
    return re.sub(r'\s+', ' ', value).strip()


def fix_numbers(data):
    """
    Fix numeric columns to actually hold numbers (or None).
    Also clear those that do not have a category.
    """

    output = []

    for row in data:
        if not row[3]:
            row[-1] = None
            row[-2] = None
            row[-3] = None

        else:
            try:
                row[-1] = to_decimal(row[-1])
                row[-2] = to_decimal(row[-2])
                row[-3] = to_decimal(row[-3])
            except:
                print('FAILED:', row, file=sys.stderr)
                raise

        output.append(row)

    return output


def to_decimal(value):
    """Convert a string to a decimal value."""

    if value == '':
        return 0

    value = re.sub(r'[^0-9.,-]', '', value)
    value = value.replace(',', '.')

    return int(Decimal(value) * 1000)


def expand_rows(data):
    """
    Expand rows to disambiguate individual columns.
    """

    output = []

    for orj, org, name, cat, ab, fb, ap in data:
        try:
            orjno = int(orj)
        except:
            orjno = None

        if re.match(r'\d+|\d+-\d+|ÚZ \d+', org):
            orgno = org
            dept = ''
        else:
            orgno = None
            dept = org

        if re.match(r'^\d+\s*-', cat):
            para = cat
            item = ''
        else:
            para = ''
            item = cat

        output.append([orjno, orgno, dept, name, para, item, ab, fb, ap])

    return output


def fold_budget(data):
    """
    Fold individual rows to a budget tree structure.
    """

    orjs = {}
    paras = {}

    current_orj = None
    current_para = None

    for orj, org, dept, name, para, item, ab, fb, ap in data:
        if orj:
            current_orj = orj
            orjs.setdefault(current_orj, [])

        if dept:
            if dept not in orjs[current_orj]:
                orjs[current_orj].append(dept)

        if para:
            m = re.match(r'^(\d+)\s*-\s*(.*)', para)
            current_para = int(m.group(1))
            paras.setdefault(current_para, {
                'nazev': m.group(2),
                'polozky': {},
                'soucty': {},
            })

            if not item:
                paras[current_para]['soucty'].setdefault(current_orj, [])
                paras[current_para]['soucty'][current_orj].append({
                    'castky': [ab, fb, ap],
                    'popis': name,
                })

        if item:
            m = re.match(r'^pol\s*\.\s*(\d+)\s*-\s*(.*)', item)

            if not ab and not fb and not ap:
                # Take the amounts from the paragraph above.
                # This should work, since is always just a single item
                # presented in this way.
                ab, fb, ap = paras[current_para]['soucty'][current_orj][-1]['castky']

            paras[current_para]['polozky'].setdefault(current_orj, [])
            paras[current_para]['polozky'][current_orj].append({
                'cislo': int(m.group(1)),
                'nazev': m.group(2),
                'popis': name,
                'castky': [ab, fb, ap],
            })

    return {'paragrafy': paras, 'orj': orjs}


def check_budget(data):
    """
    Check that the budget makes sense and add missing information about
    paragraphs and/or items that can be calculated from each other.
    """

    for para_id, para in data['paragrafy'].items():
        for orj, totals in para['soucty'].items():
            para_totals = tally_items(totals)
            item_totals = tally_items(para['polozky'].get(orj, []))

            if para_totals != [0, 0, 0] and item_totals == [0, 0, 0]:
                for total in totals:
                    para['polozky'].setdefault(orj, [])
                    para['polozky'][orj].append({
                        'cislo': 9999,
                        'nazev': 'neznámá položka',
                        'popis': total['popis'],
                        'castky': total['castky'][:],
                    })

                item_totals = tally_items(totals)

                if para_totals != item_totals:
                    print('CHYBA: nesedi součty odst. {} - {}, orj {}'
                          .format(para_id, para['nazev'], orj),
                          file=sys.stderr)

    return data


def tally_items(items):
    totals = [0] * 3

    for item in items:
        for i in range(3):
            totals[i] += item['castky'][i]

    return totals


def dump_cityvizor_items(data, file=sys.stdout):
    eventid = 0

    writer = csv.writer(file, delimiter=';')
    writer.writerow([
        'type', 'paragraph', 'item', 'event', 'amount', 'date',
        'counterpartyId', 'counterpartyName', 'description',
    ])

    for para_id, para in data['paragrafy'].items():
        for orj, items in para['polozky'].items():
            for item in items:
                eventid += 1

                writer.writerow([
                    'ROZ', str(para_id), str(item['cislo']), eventid,
                    item['castky'][1], '', '', '', item['popis'],
                ])


def dump_cityvizor_events(data, file=sys.stdout):
    eventid = 0

    writer = csv.writer(file, delimiter=';')
    writer.writerow(['srcId', 'name', 'description'])

    for para_id, para in data['paragrafy'].items():
        for orj, items in para['polozky'].items():
            for item in items:
                eventid += 1
                writer.writerow([
                    eventid,
                    item['popis'],
                    '{cislo} - {nazev}'.format(**item),
                ])


if __name__ == '__main__':
    with open(sys.argv[1]) as fp:
        reader = csv.reader(fp)
        data = list(reader)

    data = remove_junk(data)
    data = merge_cont_rows(data)
    data = fix_numbers(data)
    data = expand_rows(data)
    data = fold_budget(data)
    data = check_budget(data)

    #dump_cityvizor_items(data)
    #dump_cityvizor_events(data)

    #import yaml
    #print(yaml.dump(data, allow_unicode=True, default_flow_style=None))


# vim:set sw=4 ts=4 et:
