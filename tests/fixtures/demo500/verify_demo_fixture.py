#!/usr/bin/env python3
"""Verify WardPriceDaily synthetic fixtures without external dependencies."""
import json
from collections import Counter
from pathlib import Path

base=Path(__file__).resolve().parent
all_data=json.loads((base/'wardpricedaily_demo500_all.json').read_text(encoding='utf-8'))
rows=all_data['listings']
assert all_data['target_count']==all_data['actual_collected']==len(rows)==500
assert all_data['web_search_used'] is False
assert Counter(x['target_rank'] for x in rows)=={r:10 for r in range(1,51)}
assert Counter(x['property_type'] for x in rows)=={'DAT_O':200,'NHA_RIENG':200,'CHUNG_CU':100}
assert len({x['title'] for x in rows})==500
assert len({x['address'] for x in rows})==500
assert all(x['title'].startswith('[DEMO') for x in rows)
assert all(x['evidence_status']=='UNVERIFIED' and x['source_url'] is None and x['source_website']=='DEMO_SYNTHETIC' for x in rows)
assert all(x['price_vnd']>0 and x['area_m2']>0 for x in rows)
joined=[]
for i in range(1,11):
    obj=json.loads((base/'batches'/f'demo_group_{i:02d}_50.json').read_text(encoding='utf-8'))
    assert obj['group_id']==i and obj['actual_collected']==50 and len(obj['coverage'])==5
    joined.extend(obj['listings'])
assert joined==rows
replay=json.loads((base/'replay_rank01_duplicate_test.json').read_text(encoding='utf-8'))
assert replay['listings']==rows[:10]
stat=json.loads((base/'expected_statistics_DEMO_ONLY.json').read_text(encoding='utf-8'))
assert len(stat['statistics'])==150
assert sum(x['sample_count'] for x in stat['statistics'])==500
print('PASS: 500 synthetic entries, 50 wards, 10 each, 10 batches, replay fixtures, demo summaries, never web-verified.')
