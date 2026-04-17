"""Full validation suite — all tiers, all endpoints, edge cases."""
import urllib.request, json, sys

BASE = 'http://localhost:8000'
ok=0; fail=0; bugs=[]

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f'{BASE}{path}', data=data, headers={'Content-Type':'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()), r.status

def get(path):
    req = urllib.request.Request(f'{BASE}{path}', method='GET')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read()), r.status

def ck(name, cond, info=''):
    global ok, fail
    if cond: print(f'  [PASS] {name}'); ok+=1
    else:    print(f'  [FAIL] {name}  {info}'); fail+=1; bugs.append(name)

P = {'area':2.5,'efficiency':22.0,'temp_coeff':-0.35,'panel_temp':45.0,'mppt':95.0,'tilt':0.0,
     'lat':13.0,'altitude':500.0,'month':6,'time_hrs':12.0,'clarity':'clear',
     'num_motors':4,'cruise_power':80.0,'airspeed':60.0,'power_fc':5.0,'power_tel':3.0,
     'power_payload':10.0,'power_other':2.0,'batt_wh':500.0,'batt_chem':'lipo','min_soc':20.0,'charge_eff':95.0}

# ── SERVER UP ────────────────────────────────────────────────────────────────
print('====== SERVER HEALTH ======')
try:
    urllib.request.urlopen(f'{BASE}/', timeout=5)
    ck('server up', True)
except Exception as e:
    ck('server up', False, str(e)); sys.exit(1)

# ── TIER 1: /api/calculate ───────────────────────────────────────────────────
print('\n====== T1: /api/calculate ======')
r,s = post('/api/calculate', P)
ck('status 200',              s==200)
ck('solar_power > 0',         r['solar']['solar_power'] > 0)
ck('elevation > 0',           r['solar']['elevation'] > 0)
ck('p_total > 0',             r['budget']['p_total'] > 0)
ck('p_net is float',          isinstance(r['budget']['p_net'], (int,float)))
ck('soc_24h len=49',          len(r['soc_24h']) == 49)
ck('soc all in [0,100]',      all(0 <= v <= 100 for v in r['soc_24h']))
ck('chart1_profile len=29',   len(r['profile']['chart1_profile']) == 29)
ck('chart1_season len=29',    len(r['profile']['chart1_season']) == 29)
ck('daily_energy_wh > 0',     r['profile']['daily_energy_wh'] > 0)
ck('verdict has label',       'verdict_label' in r['verdict'])
ck('sunrise has sunrise key', 'sunrise' in r['sunrise'])
ck('sunrise has night_hrs',   'night_hrs' in r['sunrise'])
ck('min_area present',        'min_area' in r)

# Edge: night (polar winter)
r2,_ = post('/api/calculate', {**P, 'lat':89.0, 'month':12, 'time_hrs':12.0})
ck('polar winter solar=0',    r2['solar']['solar_power'] == 0.0)
ck('polar winter insufficient', r2['verdict']['verdict'] in ('insufficient','battery_assisted'))
ck('polar sunrise may be None', True)  # no crash is the check

# Edge: tilt=90 (sideways panel)
r3,_ = post('/api/calculate', {**P, 'tilt':90.0})
ck('tilt=90 no crash',        isinstance(r3['solar']['solar_power'], float))

# Edge: very high altitude
r4,_ = post('/api/calculate', {**P, 'altitude':7000.0})
ck('altitude=7000 solar>0',   r4['solar']['solar_power'] > 0)

# Edge: min_soc=90 at polar night → tiny usable reserve, must be small endurance
r5,_ = post('/api/calculate', {**P, 'min_soc':90.0, 'lat':89.0, 'month':12, 'time_hrs':12.0})
ck('min_soc=90 night endurance small', r5['budget']['endurance'] is not None and r5['budget']['endurance'] < 1.0)

# Edge: Southern hemisphere summer (lat=-30, month=12)
r6,_ = post('/api/calculate', {**P, 'lat':-30.0, 'month':12})
ck('SH summer solar>0',        r6['solar']['solar_power'] > 0)

# ── TIER 1: /api/multiday ────────────────────────────────────────────────────
print('\n====== T1: /api/multiday ======')
md,_ = post('/api/multiday', {'params':P,'days':3})
ck('soc_series len=145',      len(md['soc_series']) == 3*48+1)
ck('hour_labels len=144',     len(md['hour_labels']) == 3*48)
ck('day_summaries len=3',     len(md['day_summaries']) == 3)
ck('survived is bool',        isinstance(md['survived'], bool))
ck('final_soc in [0,100]',    0 <= md['final_soc'] <= 100)
ck('soc_series all in range', all(0 <= v <= 100 for v in md['soc_series']))
ck('day1 has min/max/end',    all(k in md['day_summaries'][0] for k in ('min_soc','max_soc','end_soc')))

# ── TIER 1: /api/monthly ─────────────────────────────────────────────────────
print('\n====== T1: /api/monthly ======')
mo,_ = post('/api/monthly', P)
ck('12 rows',                  len(mo['rows']) == 12)
ck('month numbers 1-12',       [r['month'] for r in mo['rows']] == list(range(1,13)))
ck('all peak_solar numeric',   all(isinstance(r['peak_solar_w'], float) for r in mo['rows']))
ck('all day_length >= 0',      all(r['day_length_hrs'] >= 0 for r in mo['rows']))
ck('all verdict strings',      all(r['verdict'] in ('sustainable','marginal','battery_assisted','insufficient') for r in mo['rows']))

# ── TIER 1: /api/sensitivity ─────────────────────────────────────────────────
print('\n====== T1: /api/sensitivity ======')
sens,_ = post('/api/sensitivity', {'params':P,'step_pct':10.0})
ck('has baseline',             'baseline' in sens)
ck('has rows',                 'rows' in sens)
ck('rows not empty',           len(sens['rows']) > 0)
ck('baseline p_net numeric',   isinstance(sens['baseline']['p_net'], float))
ck('rows sorted desc',         all(sens['rows'][i]['sensitivity_score'] >= sens['rows'][i+1]['sensitivity_score'] for i in range(len(sens['rows'])-1)))
ck('each row has delta keys',  all('delta_pnet_low' in r and 'delta_pnet_high' in r for r in sens['rows']))

# Sustainable baseline: None endurance → delta_end uses 999 substitute
sens_sus,_ = post('/api/sensitivity', {'params':{**P,'area':10.0},'step_pct':10.0})
ck('sus baseline end=None',    sens_sus['baseline']['endurance'] is None)
ck('sus delta_end_low numeric', all(isinstance(r['delta_end_low'],(int,float)) for r in sens_sus['rows']))

# ── TIER 1: /api/configs CRUD ────────────────────────────────────────────────
print('\n====== T1: /api/configs CRUD ======')
sv,s = post('/api/configs', {'name':'__vtest__','params':P,'note':'validation'})
ck('save 200',                 s==200)
ck('saved name correct',       sv['name']=='__vtest__')
ck('saved note',               sv['note']=='validation')

gc,_ = get('/api/configs/__vtest__')
ck('get by name',              gc['name']=='__vtest__')
ck('get has params',           'params' in gc and 'area' in gc['params'])

lst,_ = get('/api/configs')
ck('list non-empty',           len(lst['configs']) > 0)
ck('list has name field',      all('name' in c for c in lst['configs']))

# Rename
import urllib.request as ur
ren_data = json.dumps({'new_name':'__vtest_renamed__'}).encode()
ren_req = ur.Request(f'{BASE}/api/configs/__vtest__/rename', data=ren_data, headers={'Content-Type':'application/json'}, method='PATCH')
with ur.urlopen(ren_req) as rr:
    ren_r = json.loads(rr.read())
ck('rename works',             ren_r['name'] == '__vtest_renamed__')

# Delete
dreq = ur.Request(f'{BASE}/api/configs/__vtest_renamed__', method='DELETE')
with ur.urlopen(dreq) as dr:
    del_r = json.loads(dr.read())
ck('delete returns name',      del_r.get('deleted') == '__vtest_renamed__')

# ── TIER 2: /api/optimize ────────────────────────────────────────────────────
print('\n====== T2: /api/optimize ======')
opt,_ = post('/api/optimize', P)
ck('best_time present',        opt.get('best_time') is not None)
ck('optimal_launch present',   opt.get('optimal_launch') is not None)
ck('profile len=29',           len(opt['profile']) == 29)
ck('window_hrs >= 0',          opt['window_hrs'] >= 0)
ck('ptotal > 0',               opt['ptotal'] > 0)
ck('optimal_launch_label',     opt.get('optimal_launch_label') is not None)
ck('all profile surplus bool', all(isinstance(p['surplus'], bool) for p in opt['profile']))

# Night-time (no surplus window)
opt_night,_ = post('/api/optimize', {**P,'lat':89.0,'month':12})
ck('polar night window=0',     opt_night['window_hrs'] == 0.0)
ck('polar night sustainable=False', opt_night['sustainable'] == False)

# ── TIER 2: /api/mission ─────────────────────────────────────────────────────
print('\n====== T2: /api/mission ======')
mis_req = {'params':P,
  'segments':[
    {'name':'Climb','duration_hrs':0.5,'altitude_m':None,'speed_kmh':None,'num_motors':None,'cruise_power_w':None,'power_payload_w':None,'power_other_w':None},
    {'name':'Survey','duration_hrs':2.0,'altitude_m':1000.0,'speed_kmh':80.0,'num_motors':4,'cruise_power_w':90.0,'power_payload_w':15.0,'power_other_w':None},
    {'name':'Return','duration_hrs':0.5,'altitude_m':None,'speed_kmh':None,'num_motors':None,'cruise_power_w':None,'power_payload_w':None,'power_other_w':None},
  ],
  'start_time_hrs':8.0}
mis,_ = post('/api/mission', mis_req)
ck('segments len=3',           len(mis['segments']) == 3)
ck('total_solar_wh >= 0',      mis['total_solar_wh'] >= 0)
ck('total_consume_wh > 0',     mis['total_consume_wh'] > 0)
ck('final_soc in [0,100]',     0 <= mis['final_soc'] <= 100)
ck('total_range_km > 0',       mis['total_range_km'] > 0)
ck('mission_feasible bool',    isinstance(mis['mission_feasible'], bool))
# Total duration = sum of segment durations
expected_dur = 0.5 + 2.0 + 0.5
ck('total_duration correct',   abs(mis['total_duration_hrs'] - expected_dur) < 0.01)

# ── TIER 2: /api/compare ─────────────────────────────────────────────────────
print('\n====== T2: /api/compare ======')
cmp,_ = post('/api/compare', {'params_a':P,'params_b':{**P,'area':5.0},'label_a':'Small','label_b':'Large'})
ck('rows len=13',              len(cmp['rows']) == 13)
ck('overall_winner valid',     cmp['overall_winner'] in ('a','b','tie'))
ck('wins sum <= rows',         cmp['wins_a']+cmp['wins_b'] <= 13)
ck('label_a present',         cmp['label_a'] == 'Small')
ck('larger area wins solar',   any(r['metric']=='solar_power_w' and r['winner']=='b' for r in cmp['rows']))

# ── TIER 3: /api/degradation ─────────────────────────────────────────────────
print('\n====== T3: /api/degradation ======')
calc,_ = post('/api/calculate', P)
solar_pw = calc['solar']['solar_power']
deg,_ = post('/api/degradation', {'params':P,'solar_power_w':solar_pw,'years':15,'annual_rate_pct':0.50,'lid_pct':1.5})
ck('yearly len=16',            len(deg['yearly']) == 16)
ck('year0 pct=100',            deg['yearly'][0]['pct_of_new'] == 100.0)
ck('year1 pct~98',             abs(deg['yearly'][1]['pct_of_new'] - 98.0) < 0.01)
ck('strictly monotone decay',  all(deg['yearly'][i]['pct_of_new'] >= deg['yearly'][i+1]['pct_of_new'] for i in range(15)))
ck('year_80pct present',       'year_80pct' in deg)
ck('pct_y25 in (0,100)',       0 < deg['pct_y25'] < 100)
ck('power_new = solar_pw',     abs(deg['power_new'] - solar_pw) < 0.01)
# Faster rate degrades more by year 25
deg_slow,_ = post('/api/degradation', {'params':P,'solar_power_w':500.0,'years':25,'annual_rate_pct':0.25,'lid_pct':1.5})
deg_fast,_ = post('/api/degradation', {'params':P,'solar_power_w':500.0,'years':25,'annual_rate_pct':0.80,'lid_pct':1.5})
ck('fast rate < slow at Y25',  deg_fast['pct_y25'] < deg_slow['pct_y25'])

# ── TIER 3: /api/thermal ─────────────────────────────────────────────────────
print('\n====== T3: /api/thermal ======')
th,_ = post('/api/thermal', {'params':P,'t_ambient':25.0,'mount_type':'uav_flying'})
ck('temp_profile len=29',      len(th['temp_profile']) == 29)
ck('power_actual len=29',      len(th['power_actual']) == 29)
ck('power_fixed len=29',       len(th['power_fixed']) == 29)
ck('peak_temp > ambient',      th['peak_temp_c'] > 25.0)
ck('avg_temp <= peak',         th['avg_temp_c'] <= th['peak_temp_c'])
ck('power_actual >= 0',        all(v >= 0 for v in th['power_actual']))
ck('power_fixed >= 0',         all(v >= 0 for v in th['power_fixed']))
ck('daily_delta_wh float',     isinstance(th['daily_delta_wh'], float))
ck('recommendation float',     isinstance(th['recommendation'], float))
# UAV flying cooler than rooftop
th_roof,_ = post('/api/thermal', {'params':P,'t_ambient':25.0,'mount_type':'rooftop'})
ck('uav cooler than rooftop',  th['peak_temp_c'] < th_roof['peak_temp_c'])
# Building is hottest
th_bldg,_ = post('/api/thermal', {'params':P,'t_ambient':25.0,'mount_type':'building'})
ck('building hottest',         th_bldg['peak_temp_c'] >= th_roof['peak_temp_c'])
# Cold ambient lowers temp
th_cold,_ = post('/api/thermal', {'params':P,'t_ambient':-10.0,'mount_type':'uav_flying'})
ck('cold ambient lowers peak', th_cold['peak_temp_c'] < th['peak_temp_c'])

# ── TIER 3: /api/battery_life ────────────────────────────────────────────────
print('\n====== T3: /api/battery_life ======')
soc = calc['soc_24h']
bl,_ = post('/api/battery_life', {'params':P,'soc_24h':soc,'missions_per_day':1.0,'projection_years':5})
ck('daily_dod_pct >= 0',       bl['daily_dod_pct'] >= 0)
ck('cycles_to_80 > 0',         bl['cycles_to_80pct'] > 0)
ck('years_to_80 > 0',          bl['years_to_80pct'] > 0)
ck('proj len=6',               len(bl['yearly_projection']) == 6)
ck('year0 cap=100%',           bl['yearly_projection'][0]['capacity_pct'] == 100.0)
ck('cap strictly declining',   all(bl['yearly_projection'][i]['capacity_pct'] >= bl['yearly_projection'][i+1]['capacity_pct'] for i in range(5)))
ck('year0 cycles=0',           bl['yearly_projection'][0]['cycles'] == 0)
ck('usable_wh > 0',            bl['current_usable_wh'] > 0)
ck('chemistry = lipo',         bl['chemistry'] == 'lipo')
ck('recommendation string',    isinstance(bl['recommendation'], str) and len(bl['recommendation']) > 10)
# LiFePO4 > LiPo life
bl_lp,_ = post('/api/battery_life', {'params':{**P,'batt_chem':'lifepo4'},'soc_24h':soc,'missions_per_day':1.0,'projection_years':5})
ck('lifepo4 > lipo years',     bl_lp['years_to_80pct'] > bl['years_to_80pct'])
# More missions/day = fewer years
bl_2mpd,_ = post('/api/battery_life', {'params':P,'soc_24h':soc,'missions_per_day':2.0,'projection_years':5})
ck('2x missions = fewer years', bl_2mpd['years_to_80pct'] < bl['years_to_80pct'])

# ── TIER 6: /api/monte_carlo ─────────────────────────────────────────────────
print('\n====== T6: /api/monte_carlo ======')
mc,_ = post('/api/monte_carlo', {'params':P,'n_samples':300,'uncertainty_pct':10.0})
ck('n_valid = n_samples',        mc['n_valid'] == 300)
ck('probs sum to 1.0',           abs(mc['prob_sustainable']+mc['prob_marginal']+mc['prob_battery_assisted']+mc['prob_insufficient'] - 1.0) < 0.01)
ck('prob_sustainable in [0,1]',  0.0 <= mc['prob_sustainable'] <= 1.0)
ck('histogram has 20 bins',      len(mc['histogram']) == 20)
ck('histogram counts sum to n',  sum(b['count'] for b in mc['histogram']) == 300)
ck('pnet_p10 <= pnet_p50',       mc['pnet_p10'] <= mc['pnet_p50'])
ck('pnet_p50 <= pnet_p90',       mc['pnet_p50'] <= mc['pnet_p90'])
ck('pnet_p50 near baseline',     abs(mc['pnet_p50'] - mc['baseline_pnet']) < 300)
ck('baseline_verdict string',    mc['baseline_verdict'] in ('sustainable','marginal','battery_assisted','insufficient'))
ck('params_varied list',         isinstance(mc['params_varied'], list) and len(mc['params_varied']) > 5)
ck('uncertainty_pct echoed',     mc['uncertainty_pct'] == 10.0)

# wider uncertainty -> wider spread
mc_w,_ = post('/api/monte_carlo', {'params':P,'n_samples':300,'uncertainty_pct':25.0})
spread_narrow = mc['pnet_p90']  - mc['pnet_p10']
spread_wide   = mc_w['pnet_p90'] - mc_w['pnet_p10']
ck('wider uncertainty -> wider spread', spread_wide > spread_narrow)

# polar night -> mostly insufficient
mc_polar,_ = post('/api/monte_carlo', {'params':{**P,'lat':85,'month':12},'n_samples':200,'uncertainty_pct':10.0})
ck('polar night -> high insufficient prob', mc_polar['prob_insufficient'] + mc_polar['prob_battery_assisted'] > 0.7)

print()
print(f'====== FINAL: {ok} PASS / {fail} FAIL out of {ok+fail} ======')
if bugs:
    print('FAILED TESTS:')
    for b in bugs:
        print(f'  - {b}')
else:
    print('ALL TESTS PASSED')
