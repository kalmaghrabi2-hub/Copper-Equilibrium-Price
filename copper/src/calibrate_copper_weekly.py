#!/usr/bin/env python3
"""Strict benchmark-aware weekly copper calibration.

Purpose:
- Forecast next observed weekly close as a *market-implied reference layer*.
- Never equate low forecast error with structural equilibrium validation.
- Hyperparameters are selected on a validation window only.
- The latest 260 weeks are untouched final OOS.
- A strict publication gate requires economically meaningful, statistically
  significant and regime-stable superiority to persistence.
"""
from __future__ import annotations
import json, math, statistics, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/copper/data/weekly_calibration.json"
TARGET = "HG=F"
MACRO = ['GC=F', 'CL=F', 'DX-Y.NYB', '^TNX', '^VIX']
SERIES = ["LAG_COPPER_LOG"] + MACRO
START = 946684800
MIN_TRAIN = 156
VALIDATION_WEEKS = 156
FINAL_OOS_WEEKS = 260
RIDGE_CANDIDATES = [0.5, 2.0, 10.0, 50.0]
BLEND_WEIGHTS = [0.0, 0.25, 0.50, 0.75, 1.0]
MIN_R2 = 0.60
MAX_MAPE = 12.0
MIN_MSE_SKILL_PCT = 2.0
MIN_REL_MAPE_IMPROVEMENT_PCT = 1.0
MAX_DM_PVALUE = 0.05
MIN_POSITIVE_SKILL_WINDOWS = 4
REGIME_WINDOWS = 5
MIN_DIRECTION_ACCURACY_PCT = 52.5
DM_NW_LAG = 4
UA = "Mozilla/5.0 CopperEquilibriumPrice/3.0"

def chart(symbol: str):
    q = urllib.parse.quote(symbol, safe="")
    now = int(datetime.now(timezone.utc).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{q}"
           f"?period1={START}&period2={now}&interval=1wk&events=history"
           "&includeAdjustedClose=true")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo returned no data for {symbol}")
    ts = result.get("timestamp") or []
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
    out = {}
    for t, value in zip(ts, closes):
        if value is None: continue
        value = float(value)
        if value > 0 and math.isfinite(value): out[int(t) // 604800] = value
    return out, url

def solve(a, b):
    n = len(b); aug = [a[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col])); aug[col], aug[pivot] = aug[pivot], aug[col]
        z = aug[col][col]
        if abs(z) < 1e-12: raise RuntimeError("singular matrix")
        aug[col] = [v / z for v in aug[col]]
        for row in range(n):
            if row == col: continue
            f = aug[row][col]; aug[row] = [aug[row][j] - f * aug[col][j] for j in range(n + 1)]
    return [aug[i][-1] for i in range(n)]

def design(rows):
    cols = list(zip(*[r[2] for r in rows])); means = [statistics.fmean(c) for c in cols]; sds = [statistics.pstdev(c) or 1.0 for c in cols]
    return [[1.0] + [(v-m)/s for v,m,s in zip(r[2], means, sds)] for r in rows], means, sds

def fit(x_rows, y, lam):
    p = len(x_rows[0]); a = [[0.0]*p for _ in range(p)]; b = [0.0]*p
    for x, target in zip(x_rows, y):
        for i in range(p):
            b[i] += x[i]*target
            for j in range(p): a[i][j] += x[i]*x[j]
    for i in range(1,p): a[i][i] += lam
    return solve(a,b)

def predict_one(train, row, lam):
    x, means, sds = design(train); beta = fit(x, [math.log(r[1]) for r in train], lam)
    lx = [1.0] + [(v-m)/s for v,m,s in zip(row[2], means, sds)]
    return math.exp(sum(a*b for a,b in zip(lx,beta)))

def blended(raw, naive, weight): return naive + weight*(raw-naive)

def metric_block(pred, actual, naive):
    mse = statistics.fmean((a-p)**2 for a,p in zip(actual,pred)); nmse = statistics.fmean((a-p)**2 for a,p in zip(actual,naive))
    mape = 100*statistics.fmean(abs((a-p)/a) for a,p in zip(actual,pred)); naive_mape = 100*statistics.fmean(abs((a-p)/a) for a,p in zip(actual,naive))
    ma = statistics.fmean(actual); denom = sum((a-ma)**2 for a in actual); r2 = 1 - sum((a-p)**2 for a,p in zip(actual,pred))/denom if denom else 0.0
    hits = n_dir = 0
    for a,p,n in zip(actual,pred,naive):
        realized = a-n; signaled = p-n
        if realized != 0: n_dir += 1; hits += int((realized>0)==(signaled>0))
    direction = 100*hits/n_dir if n_dir else None; rel = 100*(naive_mape-mape)/naive_mape if naive_mape else 0.0
    return {"n":len(actual),"r2":round(r2,4),"mape_pct":round(mape,3),"fit_score_100_minus_mape_pct":round(max(0,min(100,100-mape)),3),"accuracy_pct":round(max(0,min(100,100-mape)),3),"rmse_usd_lb":round(math.sqrt(mse),3),"naive_mape_pct":round(naive_mape,3),"naive_fit_score_100_minus_mape_pct":round(max(0,min(100,100-naive_mape)),3),"naive_accuracy_pct":round(max(0,min(100,100-naive_mape)),3),"naive_rmse_usd_lb":round(math.sqrt(nmse),3),"skill_vs_naive_mse_pct":round(100*(1-mse/nmse) if nmse>0 else 0.0,3),"relative_mape_improvement_pct":round(rel,3),"direction_accuracy_pct":None if direction is None else round(direction,2)}

def dm_test(pred, actual, naive, lag=4):
    d = [(a-n)**2 - (a-p)**2 for a,p,n in zip(actual,pred,naive)]; n=len(d); md=statistics.fmean(d); c=[x-md for x in d]; g0=sum(x*x for x in c)/n; lrv=g0; ml=min(lag,n-1)
    for k in range(1,ml+1):
        g=sum(c[t]*c[t-k] for t in range(k,n))/n; lrv += 2*(1-k/(ml+1))*g
    if lrv<=0: stat,p=0.0,1.0
    else: stat=md/math.sqrt(lrv/n); p=0.5*math.erfc(stat/math.sqrt(2.0))
    return {"newey_west_lag":ml,"statistic":round(stat,4),"one_sided_p_value":round(p,6),"mean_loss_advantage":md}

def regime_test(pred,actual,naive,dates):
    size=len(actual)//REGIME_WINDOWS; windows=[]; positives=0
    for j in range(REGIME_WINDOWS):
        lo=j*size; hi=(j+1)*size if j<REGIME_WINDOWS-1 else len(actual); mm=metric_block(pred[lo:hi],actual[lo:hi],naive[lo:hi]); pos=mm["skill_vs_naive_mse_pct"]>0 and mm["mape_pct"]<mm["naive_mape_pct"]; positives += int(pos)
        windows.append({"start":dates[lo],"end":dates[hi-1],"skill_vs_naive_mse_pct":mm["skill_vs_naive_mse_pct"],"mape_pct":mm["mape_pct"],"naive_mape_pct":mm["naive_mape_pct"],"positive_skill":pos})
    return {"windows":windows,"positive_skill_windows":positives,"required_positive_skill_windows":MIN_POSITIVE_SKILL_WINDOWS}

def quantile(values,q):
    vals=sorted(values); pos=(len(vals)-1)*q; lo=int(math.floor(pos)); hi=int(math.ceil(pos))
    return vals[lo] if lo==hi else vals[lo]+(vals[hi]-vals[lo])*(pos-lo)

def interval(center,errors,lq,hq): return [round(center*math.exp(quantile(errors,lq)),4),round(center*math.exp(quantile(errors,hq)),4)]

def main():
    target,target_url=chart(TARGET); factors={}; urls={}
    for symbol in MACRO: factors[symbol],urls[symbol]=chart(symbol)
    common=sorted(set(target).intersection(*[set(factors[s]) for s in MACRO])); raw=[(w,target[w],[factors[s][w] for s in MACRO]) for w in common]; rows=[]
    for i in range(1,len(raw)):
        pw,prev,pm=raw[i-1]; w,cur,_=raw[i]
        if w-pw==1: rows.append((w,cur,[math.log(prev)]+pm))
    required=MIN_TRAIN+VALIDATION_WEEKS+FINAL_OOS_WEEKS
    if len(rows)<required: raise RuntimeError(f"insufficient complete weekly history: {len(rows)} < {required}")
    test_start=len(rows)-FINAL_OOS_WEEKS; val_start=test_start-VALIDATION_WEEKS
    cache={lam:{i:predict_one(rows[:i],rows[i],lam) for i in range(val_start,len(rows))} for lam in RIDGE_CANDIDATES}
    candidates=[]
    for lam in RIDGE_CANDIDATES:
        for weight in BLEND_WEIGHTS:
            p=[];a=[];n=[]
            for i in range(val_start,test_start):
                anchor=math.exp(rows[i][2][0]); p.append(blended(cache[lam][i],anchor,weight)); a.append(rows[i][1]); n.append(anchor)
            candidates.append({"ridge_lambda":lam,"blend_weight":weight,"validation":metric_block(p,a,n)})
    candidates.sort(key=lambda c:(c["validation"]["rmse_usd_lb"],c["validation"]["mape_pct"],c["blend_weight"])); selected=candidates[0]; lam=selected["ridge_lambda"]; weight=selected["blend_weight"]
    pred=[];actual=[];naive=[];dates=[]
    for i in range(test_start,len(rows)):
        anchor=math.exp(rows[i][2][0]); pred.append(blended(cache[lam][i],anchor,weight)); actual.append(rows[i][1]); naive.append(anchor); dates.append(datetime.fromtimestamp(rows[i][0]*604800,tz=timezone.utc).date().isoformat())
    metrics=metric_block(pred,actual,naive); metrics.update({"n_weeks_total":len(rows),"walk_forward_n":len(pred),"walk_forward_start":dates[0],"walk_forward_end":dates[-1]}); dm=dm_test(pred,actual,naive,DM_NW_LAG); regimes=regime_test(pred,actual,naive,dates)
    x_all,means,sds=design(rows); beta=fit(x_all,[math.log(r[1]) for r in rows],lam); last_week,last_price,last_macro=raw[-1]; lv=[math.log(last_price)]+last_macro; lx=[1.0]+[(v-m)/s for v,m,s in zip(lv,means,sds)]; raw_live=math.exp(sum(a*b for a,b in zip(lx,beta))); live_value=blended(raw_live,last_price,weight)
    me=[math.log(a/p) for a,p in zip(actual,pred)]; ne=[math.log(a/n) for a,n in zip(actual,naive)]; c80=interval(live_value,me,.10,.90); c95=interval(live_value,me,.025,.975); n80=interval(last_price,ne,.10,.90); n95=interval(last_price,ne,.025,.975)
    basic=metrics["r2"]>=MIN_R2 and metrics["mape_pct"]<=MAX_MAPE; checks={"nonzero_model_weight":weight>0,"min_mse_skill":metrics["skill_vs_naive_mse_pct"]>=MIN_MSE_SKILL_PCT,"min_relative_mape_improvement":metrics["relative_mape_improvement_pct"]>=MIN_REL_MAPE_IMPROVEMENT_PCT,"dm_significance":dm["one_sided_p_value"]<=MAX_DM_PVALUE,"regime_stability":regimes["positive_skill_windows"]>=MIN_POSITIVE_SKILL_WINDOWS,"directional_information":(metrics["direction_accuracy_pct"] or 0)>=MIN_DIRECTION_ACCURACY_PCT,"basic_fit":basic}; strict=all(checks.values())
    output={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"model":"copper-weekly-strict-governance-v3","frequency":"weekly","forecast_horizon_weeks":1,"model_role":"near_term_market_reference_not_structural_equilibrium","target":TARGET,"target_source":target_url,"series":SERIES,"predictor_sources":{"LAG_COPPER_LOG":target_url,**urls},"beta":beta,"means":means,"sds":sds,"ridge_lambda":lam,"blend_weight_vs_persistence":weight,"selection":{"protocol":"validation-only hyperparameter/blend selection; final 260 weeks untouched","validation_weeks":VALIDATION_WEEKS,"final_oos_weeks":FINAL_OOS_WEEKS,"ridge_candidates":RIDGE_CANDIDATES,"blend_weights":BLEND_WEIGHTS,"selected_validation_metrics":selected["validation"]},"metrics":metrics,"diebold_mariano_vs_persistence":dm,"regime_stability":regimes,"walk_forward_gate":"PASS" if basic else "FAIL","benchmark_gate":"PASS" if (weight>0 and metrics["skill_vs_naive_mse_pct"]>0 and metrics["mape_pct"]<metrics["naive_mape_pct"]) else "FAIL","strict_publication_gate":"PASS" if strict else "FAIL","publication_status":"VALIDATED" if strict else "REFERENCE_ONLY","strict_governance":{"checks":checks,"failed_checks":[k for k,v in checks.items() if not v],"thresholds":{"min_mse_skill_pct":MIN_MSE_SKILL_PCT,"min_relative_mape_improvement_pct":MIN_REL_MAPE_IMPROVEMENT_PCT,"max_dm_one_sided_p_value":MAX_DM_PVALUE,"min_positive_skill_windows":MIN_POSITIVE_SKILL_WINDOWS,"regime_windows":REGIME_WINDOWS,"min_direction_accuracy_pct":MIN_DIRECTION_ACCURACY_PCT},"rule":"No candidate may be published as validated equilibrium/reference unless every hard gate passes."},"uncertainty":{"method":"empirical final-OOS log forecast errors; descriptive prediction interval","candidate_80_pct_interval":c80,"candidate_95_pct_interval":c95,"persistence_80_pct_interval":n80,"persistence_95_pct_interval":n95,"candidate_80_pct_interval_usd_t":[round(x*2204.62262185,2) for x in c80],"candidate_95_pct_interval_usd_t":[round(x*2204.62262185,2) for x in c95],"persistence_80_pct_interval_usd_t":[round(x*2204.62262185,2) for x in n80],"persistence_95_pct_interval_usd_t":[round(x*2204.62262185,2) for x in n95]},"live":{"as_of_week":datetime.fromtimestamp(last_week*604800,tz=timezone.utc).date().isoformat(),"anchor_usd_lb":round(last_price,6),"raw_model_fair_value_usd_lb":round(raw_live,6),"raw_model_fair_value_usd_t":round(raw_live*2204.62262185,2),"fair_value_usd_lb":round(live_value,6),"fair_value_usd_t":round(live_value*2204.62262185,2),"predicted_return_pct":round((live_value/last_price-1)*100,3)},"rules":{"min_training_weeks":MIN_TRAIN,"validation_weeks":VALIDATION_WEEKS,"final_oos_weeks":FINAL_OOS_WEEKS,"max_mape_pct":MAX_MAPE,"min_r2":MIN_R2,"naive_benchmark":"persistence: next weekly close equals previous observed weekly close","fit_score_definition":"100 - final OOS MAPE; descriptive fit score, NOT probability and NOT proof of equilibrium accuracy","lookahead":"none","missing_data":"complete-case only; no imputation","equilibrium_claim_rule":"weekly forecast layer alone cannot validate structural equilibrium; structural/physical overlays require separate OOS validation."}}
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(output,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
