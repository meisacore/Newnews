-- Installed into each private norx_* schema. All functions use the caller's
-- transaction and permissions; none are SECURITY DEFINER or exposed to browsers.
CREATE TABLE IF NOT EXISTS cloud_runtime (
  id integer PRIMARY KEY CHECK (id=1),
  active_until bigint NOT NULL DEFAULT 0,
  next_batch_at bigint NOT NULL DEFAULT 0,
  snapshot jsonb,
  snapshot_at bigint NOT NULL DEFAULT 0
);
ALTER TABLE cloud_runtime ENABLE ROW LEVEL SECURITY;
INSERT INTO cloud_runtime(id) VALUES(1) ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION norx_amount(x bigint,y bigint,s text,q bigint)
RETURNS bigint LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE n numeric;
BEGIN
  IF q IS NULL OR q<=0 THEN RAISE EXCEPTION 'Quantity must be a positive whole number' USING ERRCODE='P0001'; END IF;
  IF s='buy' THEN
    IF q>=x THEN RAISE EXCEPTION 'Insufficient liquidity' USING ERRCODE='P0001'; END IF;
    n:=ceil(y::numeric*q/(x-q));
    RETURN ceil(n*10000/9970)::bigint;
  ELSIF s='sell' THEN
    RETURN floor(floor(y::numeric*q/(x::numeric+q))*9970/10000)::bigint;
  END IF;
  RAISE EXCEPTION 'Invalid side' USING ERRCODE='P0001';
END $$;

CREATE OR REPLACE FUNCTION norx_quantity(x bigint,y bigint,b bigint)
RETURNS bigint LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE lo bigint:=0; hi bigint:=x-1; mid bigint;
BEGIN
  WHILE lo<hi LOOP
    mid:=(lo+hi+1)/2;
    IF norx_amount(x,y,'buy',mid)<=b THEN lo:=mid; ELSE hi:=mid-1; END IF;
  END LOOP;
  RETURN lo;
END $$;

CREATE OR REPLACE FUNCTION norx_trade(who text,token text,s text,q bigint,why text)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE c coins%ROWTYPE; paid bigint; trade_id bigint; execution double precision;
BEGIN
  SELECT * INTO STRICT c FROM coins WHERE id=token;
  paid:=norx_amount(c.tokens,c.cash,s,q);
  IF paid<=0 THEN RAISE EXCEPTION 'Trade too small' USING ERRCODE='P0001'; END IF;
  IF s='buy' THEN
    UPDATE accounts SET cash=cash-paid WHERE id=who AND cash>=paid;
    IF NOT FOUND THEN RAISE EXCEPTION 'Insufficient USD' USING ERRCODE='P0001'; END IF;
    INSERT INTO holdings(account,coin,qty) VALUES(who,token,q)
      ON CONFLICT(account,coin) DO UPDATE SET qty=holdings.qty+excluded.qty;
    UPDATE coins SET cash=cash+paid,tokens=tokens-q WHERE id=token;
  ELSE
    UPDATE holdings SET qty=qty-q WHERE account=who AND coin=token AND qty>=q;
    IF NOT FOUND THEN RAISE EXCEPTION 'Insufficient tokens' USING ERRCODE='P0001'; END IF;
    UPDATE accounts SET cash=cash+paid WHERE id=who;
    UPDATE coins SET cash=cash-paid,tokens=tokens+q WHERE id=token;
  END IF;
  execution:=paid::double precision/1000000/q*CASE WHEN s='buy' THEN .997 ELSE 1/.997 END;
  INSERT INTO trades(ts,account,coin,side,qty,amount,price,reason)
    VALUES(floor(extract(epoch FROM clock_timestamp()))::bigint,who,token,s,q,paid,execution,why)
    RETURNING id INTO trade_id;
  RETURN jsonb_build_object('trade_id',trade_id,'coin',token,'side',s,'qty',q,'usd',paid::double precision/1000000);
END $$;

CREATE OR REPLACE FUNCTION norx_quote(who text,token text,s text,b bigint,q bigint,quote_id text)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE c coins%ROWTYPE; available bigint; paid bigint; expiry bigint;
BEGIN
  SELECT * INTO c FROM coins WHERE id=token;
  IF NOT FOUND THEN RAISE EXCEPTION 'Unknown coin' USING ERRCODE='P0001'; END IF;
  INSERT INTO accounts(id,cash,kind) VALUES(who,10000000000,'human') ON CONFLICT DO NOTHING;
  SELECT cash INTO available FROM accounts WHERE id=who;
  IF s='buy' THEN
    IF b IS NULL OR b<=0 OR b>available THEN RAISE EXCEPTION 'Invalid budget or insufficient USD' USING ERRCODE='P0001'; END IF;
    q:=norx_quantity(c.tokens,c.cash,b);
  ELSIF s='sell' THEN
    SELECT qty INTO available FROM holdings WHERE account=who AND coin=token;
    IF available IS NULL OR q>available THEN RAISE EXCEPTION 'Insufficient tokens' USING ERRCODE='P0001'; END IF;
  ELSE RAISE EXCEPTION 'Invalid side' USING ERRCODE='P0001';
  END IF;
  paid:=norx_amount(c.tokens,c.cash,s,q);
  IF paid<=0 THEN RAISE EXCEPTION 'Trade too small' USING ERRCODE='P0001'; END IF;
  expiry:=floor(extract(epoch FROM clock_timestamp()))::bigint+30;
  INSERT INTO quotes(id,account,coin,side,qty,amount,expires) VALUES(quote_id,who,token,s,q,paid,expiry);
  RETURN jsonb_build_object('id',quote_id,'coin',token,'side',s,'qty',q,'amount',paid,'usd',paid::double precision/1000000,'expires',expiry,'slippage_bps',100);
END $$;

CREATE OR REPLACE FUNCTION norx_execute(who text,quote_id text,rid text)
RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE q quotes%ROWTYPE; c coins%ROWTYPE; paid bigint; receipt jsonb;
BEGIN
  SELECT * INTO q FROM quotes WHERE id=quote_id AND account=who;
  IF NOT FOUND THEN RAISE EXCEPTION 'Unknown quote' USING ERRCODE='P0001'; END IF;
  IF q.result IS NOT NULL THEN RETURN q.result::jsonb; END IF;
  IF EXISTS(SELECT 1 FROM quotes WHERE request_id=rid) THEN RAISE EXCEPTION 'Request ID already used; request a fresh quote' USING ERRCODE='P0001'; END IF;
  IF q.expires<extract(epoch FROM clock_timestamp()) THEN RAISE EXCEPTION 'Quote expired; request a new quote' USING ERRCODE='P0001'; END IF;
  SELECT * INTO STRICT c FROM coins WHERE id=q.coin;
  paid:=norx_amount(c.tokens,c.cash,q.side,q.qty);
  IF (q.side='buy' AND paid>q.amount) OR (q.side='sell' AND paid::numeric*10000<q.amount::numeric*9900)
    THEN RAISE EXCEPTION 'Price moved outside your limit; request a new quote' USING ERRCODE='P0001'; END IF;
  receipt:=norx_trade(who,q.coin,q.side,q.qty,'Player trade');
  UPDATE quotes SET request_id=rid,result=receipt::text WHERE id=q.id;
  UPDATE cloud_runtime SET next_batch_at=0 WHERE id=1;
  RETURN receipt;
END $$;

-- Short batches replace the always-on Python loop. A transaction-scoped lock
-- shared with the Python engine is acquired by the Worker before calling this.
CREATE OR REPLACE FUNCTION norx_batch(now_s bigint,scenario jsonb,policies jsonb)
RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
  due bigint; seq bigint; tick_no bigint; condition_name text;
  a record; c coins%ROWTYPE; position record; entry record;
  p jsonb; persona text; target double precision; estimate double precision;
  price double precision; exposure double precision; equity double precision;
  held bigint; gap double precision; band double precision; budget bigint;
  q bigint; lo bigint; hi bigint; mid bigint; paid bigint; cash_balance bigint;
  reason text; token text; new_ref double precision; old_spot double precision;
  gain double precision; age double precision; impatient boolean; done integer:=0;
  adjective text; noun text; seed bigint; pool bigint; fraction double precision;
  adjectives text[]:=ARRAY['Cosmic','Lunar','Velvet','Solar','Neon','Golden','Tiny','Orbit','Midnight','Pixel','Electric','Crystal','Lucky','Dream','Turbo','Silver'];
  nouns text[]:=ARRAY['Otter','Fox','Comet','Panda','Moth','Peach','Whale','Koala','Cloud','Kiwi','Nova','Gecko','Duck','Tiger','Echo','Lotus'];
BEGIN
  SELECT value::bigint INTO due FROM meta WHERE key='next_launch_at';
  SELECT value::bigint INTO seq FROM meta WHERE key='launch_sequence';
  IF now_s>=due THEN
    FOR i IN 1..5 LOOP
      seq:=seq+1; token:='coin-'||lpad(seq::text,8,'0');
      adjective:=adjectives[1+floor(random()*16)::int]; noun:=nouns[1+floor(random()*16)::int];
      seed:=(1500+floor(random()*10501)::bigint)*1000000;
      pool:=(50000+floor(random()*150001)::bigint)*1000;
      INSERT INTO coins(id,name,symbol,cash,tokens,reference)
        VALUES(token,adjective||' '||noun,upper(left(adjective,2)||left(noun,2)||to_hex(seq)),seed,pool,seed::double precision/pool/1000000);
      INSERT INTO holdings VALUES('treasury',token,1000000000-pool);
      INSERT INTO launches VALUES(token,now_s,seed,seed);
    END LOOP;
    UPDATE meta SET value=seq::text WHERE key='launch_sequence';
    UPDATE meta SET value=(now_s+60)::text WHERE key='next_launch_at';
  END IF;
  SELECT value::bigint+1 INTO tick_no FROM meta WHERE key='tick';
  UPDATE meta SET value=tick_no::text WHERE key='tick';
  SELECT value INTO condition_name FROM meta WHERE key='condition';
  IF random()<.008 THEN
    condition_name:=(ARRAY['calm','optimistic','stressed'])[1+floor(random()*3)::int];
    UPDATE meta SET value=condition_name WHERE key='condition';
  END IF;
  -- Random cohorts keep every one of the 2,000 agents eligible, but bound work.
  FOR a IN SELECT ac.*,ap.name,ap.persona FROM accounts ac JOIN agent_personas ap ON ap.account=ac.id
    WHERE ac.kind='agent' AND ap.next_tick<=tick_no ORDER BY random() LIMIT 256
  LOOP
    p:=policies->a.persona; persona:=a.persona;
    IF p IS NULL OR random()>least(1,(p->>6)::double precision*(scenario->>'activity')::double precision) THEN CONTINUE; END IF;
    token:=NULL;
    IF random()<.7 THEN SELECT coin INTO token FROM holdings WHERE account=a.id AND qty>0 ORDER BY random() LIMIT 1; END IF;
    IF token IS NULL THEN
      SELECT id INTO token FROM (SELECT c0.id FROM coins c0 JOIN launches l ON l.coin=c0.id ORDER BY l.created_at DESC,c0.id DESC LIMIT 40) latest ORDER BY random() LIMIT 1;
    END IF;
    IF token IS NULL THEN CONTINUE; END IF;
    SELECT * INTO STRICT c FROM coins WHERE id=token;
    old_spot:=c.cash::double precision/c.tokens;
    price:=old_spot/1000000;
    new_ref:=greatest(.000001,c.reference*exp((scenario->>'drift')::double precision+
      CASE condition_name WHEN 'optimistic' THEN .0001 WHEN 'stressed' THEN -.0001 ELSE 0 END+
      sqrt(-2*ln(greatest(random(),.000000001)))*cos(2*pi()*random())*
      CASE WHEN (scenario->>'activity')::double precision>1.5 THEN .005 ELSE .002 END));
    UPDATE coins SET reference=new_ref WHERE id=token;
    SELECT cash INTO cash_balance FROM accounts WHERE id=a.id;
    held:=0; equity:=cash_balance;
    FOR position IN SELECT h.qty,c1.* FROM holdings h JOIN coins c1 ON c1.id=h.coin WHERE h.account=a.id AND h.qty>0 LOOP
      equity:=equity+norx_amount(position.tokens,position.cash,'sell',position.qty);
      IF position.id=token THEN held:=position.qty; END IF;
    END LOOP;
    exposure:=CASE WHEN held>0 THEN norx_amount(c.tokens,c.cash,'sell',held) ELSE 0 END;
    target:=NULL; estimate:=NULL;
    IF persona IN ('patient_value','contrarian') THEN
      estimate:=new_ref*exp(sqrt(-2*ln(greatest(random(),.000000001)))*cos(2*pi()*random())*.012);
      target:=(p->>2)::double precision*least(1,greatest(0,(ln(estimate/price)-.008-CASE WHEN persona='contrarian' THEN 5*c.momentum ELSE 0 END)/.12));
      reason:='buy at a perceived discount; otherwise hold or reduce exposure';
    ELSIF persona='careful_trend' THEN
      target:=(p->>2)::double precision*least(1,greatest(0,(c.momentum-.001)*35));
      estimate:=price*exp(least(.12,greatest(-.12,c.momentum*8)));
      reason:='follow a sustained trend only when execution costs leave an edge';
    ELSIF persona='fomo' THEN
      IF held>0 AND (c.momentum<-.003 OR random()<.08) THEN target:=0;
      ELSIF c.momentum>.001 OR random()<.12 THEN target:=(p->>2)::double precision*(.65+random()*.35); END IF;
      reason:='chase excitement or panic after a reversal';
    ELSIF persona='reckless_whale' THEN
      fraction:=random();
      IF fraction<.62 THEN target:=(p->>2)::double precision*(.7+random()*.3);
      ELSIF fraction<.9 AND held>0 THEN target:=0; END IF;
      reason:='make or abandon an oversized speculative bet';
    ELSIF persona='gambler' THEN
      IF held>0 AND random()<.3 THEN target:=0;
      ELSE target:=(p->>2)::double precision*(ARRAY[0,.3,.7,1])[1+floor(random()*4)::int]; END IF;
      reason:='make a speculative bet without a valuation check';
    ELSE
      IF random()>=.35 THEN target:=(p->>2)::double precision*random(); END IF;
      reason:='make a small discretionary trade';
    END IF;
    IF held>0 THEN
      SELECT sum(amount)::double precision/sum(qty)/1000000 AS cost,max(ts) AS entered INTO entry
        FROM trades WHERE account=a.id AND coin=token AND side='buy';
      IF entry.cost>0 THEN
        gain:=price/entry.cost-1; age:=greatest(0,now_s-entry.entered); impatient:=NOT (p->>9)::boolean;
        IF gain>(CASE WHEN impatient THEN .20 ELSE .35 END) OR gain<(CASE WHEN impatient THEN -.15 ELSE -.25 END) OR
          (age>(CASE WHEN impatient THEN 180 ELSE 900 END) AND random()<.35) THEN
          target:=0; estimate:=NULL; reason:='take profit, cut losses or rotate an aging position';
        END IF;
      END IF;
    END IF;
    IF target IS NULL THEN CONTINUE; END IF;
    target:=target*(scenario->>'appetite')::double precision;
    gap:=target*equity-exposure; band:=greatest(1000000,equity*.001); q:=0;
    IF gap>band THEN
      budget:=floor(least(gap,cash_balance*((p->>3)::double precision+random()*((p->>4)::double precision-(p->>3)::double precision)),c.cash*CASE WHEN persona='reckless_whale' THEN .15 ELSE .06 END));
      lo:=0; hi:=norx_quantity(c.tokens,c.cash,greatest(0,budget));
      WHILE lo<hi LOOP
        mid:=(lo+hi+1)/2; paid:=norx_amount(c.tokens,c.cash,'buy',mid);
        IF paid::double precision/mid<=old_spot*(1+(p->>5)::double precision/10000) AND
          (NOT (p->>9)::boolean OR (estimate IS NOT NULL AND paid::double precision/mid<=estimate*1000000*.995))
          THEN lo:=mid; ELSE hi:=mid-1; END IF;
      END LOOP;
      q:=lo;
      IF q>0 THEN PERFORM norx_trade(a.id,token,'buy',q,a.name||' · '||(p->>0)||': '||reason); END IF;
    ELSIF gap < -band AND held>0 THEN
      q:=CASE WHEN target=0 THEN held ELSE least(held,greatest(1,floor(held*least(1,-gap/greatest(1,exposure)))::bigint)) END;
      IF norx_amount(c.tokens,c.cash,'sell',q)>0 THEN PERFORM norx_trade(a.id,token,'sell',q,a.name||' · '||(p->>0)||': '||reason); ELSE q:=0; END IF;
    END IF;
    IF q>0 THEN
      done:=done+1;
      UPDATE agent_personas SET next_tick=tick_no+(p->>7)::int+floor(random()*((p->>8)::int-(p->>7)::int+1))::int WHERE account=a.id;
      UPDATE coins SET momentum=.8*c.momentum+.2*ln((cash::double precision/tokens)/old_spot) WHERE id=token;
    END IF;
  END LOOP;
  DELETE FROM quotes WHERE result IS NULL AND expires<now_s-3600;
  INSERT INTO meta VALUES('last_tick_at',now_s::text) ON CONFLICT(key) DO UPDATE SET value=excluded.value;
  RETURN done;
END $$;

REVOKE ALL ON cloud_runtime FROM PUBLIC;
REVOKE ALL ON FUNCTION norx_amount(bigint,bigint,text,bigint),norx_quantity(bigint,bigint,bigint),
  norx_trade(text,text,text,bigint,text),norx_quote(text,text,text,bigint,bigint,text),
  norx_execute(text,text,text),norx_batch(bigint,jsonb,jsonb) FROM PUBLIC;

-- Keep aggregation/JSON assembly in PostgreSQL. Workers Free has a very small
-- CPU budget: thousands of pg rows and repeated JSON copies cannot run there.
CREATE OR REPLACE FUNCTION norx_policy_label(persona text)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE persona WHEN 'patient_value' THEN 'Patient value investor'
    WHEN 'careful_trend' THEN 'Disciplined trend trader' WHEN 'contrarian' THEN 'Cautious contrarian'
    WHEN 'fomo' THEN 'FOMO chaser' WHEN 'gambler' THEN 'Impulsive gambler'
    WHEN 'reckless_whale' THEN 'Reckless whale' WHEN 'retail_noise' THEN 'Casual small trader' END
$$;

CREATE OR REPLACE FUNCTION norx_public_trades(token text DEFAULT NULL,minimum bigint DEFAULT 0,row_limit integer DEFAULT 30)
RETURNS jsonb LANGUAGE sql STABLE AS $$
  SELECT coalesce(jsonb_agg(value ORDER BY id DESC),'[]'::jsonb) FROM (
    SELECT t.id,to_jsonb(t)||jsonb_build_object(
      'account',CASE WHEN p.account IS NULL THEN 'Player' ELSE t.account END,
      'agent_name',coalesce(p.name,'Player'),'persona',norx_policy_label(p.persona)) AS value
    FROM trades t LEFT JOIN agent_personas p ON p.account=t.account
    WHERE (token IS NULL OR t.coin=token) AND t.amount>=minimum
    ORDER BY t.id DESC LIMIT row_limit
  ) public_rows
$$;

CREATE OR REPLACE FUNCTION norx_coin_data(now_s bigint,selected_token text DEFAULT NULL)
RETURNS jsonb LANGUAGE sql STABLE AS $$
WITH periods(label,seconds) AS (VALUES('5m',300),('1h',3600),('6h',21600),('24h',86400)),
window_sums AS MATERIALIZED (
 SELECT w.label,t.coin,sum(CASE WHEN side='buy' THEN amount ELSE 0 END)::double precision/1000000 AS buys,
   sum(CASE WHEN side='sell' THEN amount ELSE 0 END)::double precision/1000000 AS sells,
   count(*) FILTER(WHERE side='buy') AS buy_count,count(*) FILTER(WHERE side='sell') AS sell_count,
   count(DISTINCT account) FILTER(WHERE side='buy') AS buyers,count(DISTINCT account) AS traders,
   count(*) AS txns,sum(amount)::double precision/1000000 AS volume
 FROM periods w JOIN trades t ON t.ts>=now_s-w.seconds AND t.ts<=now_s
 WHERE selected_token IS NULL OR t.coin=selected_token GROUP BY w.label,t.coin
),stats AS MATERIALIZED (
 SELECT *,buys*(ln((2+buyers)::double precision)/ln(2::double precision))*buy_count/greatest(1,txns) AS score FROM window_sums
),heat AS (
 SELECT *,row_number() OVER(PARTITION BY label ORDER BY score DESC,coin) AS ranking FROM stats
),hot AS (SELECT DISTINCT coin FROM heat WHERE ranking<=60),
base AS (
 SELECT c.*,l.created_at,l.activity_goal,l.seed_cash,
   c.cash::double precision/c.tokens/1000000 AS price,
   1000000000-(SELECT qty FROM holdings WHERE account='treasury' AND coin=c.id) AS circulation,
   coalesce(t.volume,0) AS total_volume,coalesce(t.volume_24h,0) AS volume_24h,
   coalesce(t.txns,0) AS txns,coalesce(h.holders,0) AS holders,
   (SELECT price FROM trades WHERE coin=c.id AND ts>=now_s-86400 ORDER BY ts,id LIMIT 1) AS first_price
 FROM coins c JOIN launches l ON l.coin=c.id
 LEFT JOIN (SELECT coin,sum(amount) AS volume,sum(amount) FILTER(WHERE ts>=now_s-86400) AS volume_24h,count(*) AS txns
   FROM trades WHERE selected_token IS NULL OR coin=selected_token GROUP BY coin) t ON t.coin=c.id
 LEFT JOIN (SELECT coin,count(*) AS holders FROM holdings WHERE account!='treasury' AND qty>0
   AND (selected_token IS NULL OR coin=selected_token) GROUP BY coin) h ON h.coin=c.id
 WHERE selected_token IS NULL OR c.id=selected_token
),progressed AS (
 SELECT *,least(100,total_volume::double precision/activity_goal*100) AS progress FROM base
),staged AS (
 SELECT *,CASE WHEN progress>=100 THEN 'migrated' WHEN progress>=70 THEN 'stretch' ELSE 'new' END AS stage FROM progressed
),ranked AS (
 SELECT *,row_number() OVER(PARTITION BY stage ORDER BY created_at DESC,id) AS rn FROM staged
),candidates AS (
 SELECT r.* FROM ranked r WHERE rn<=60 OR id=selected_token OR id IN(SELECT coin FROM hot)
),rendered AS MATERIALIZED (
 SELECT c.id,c.created_at,c.rn,c.id=selected_token AS selected,c.id IN(SELECT coin FROM hot) AS is_hot,
   coalesce(s.score,0) AS score,
   jsonb_build_object('id',c.id,'name',c.name,'symbol',c.symbol,'price',c.price,
     'circulating_supply',c.circulation,'total_supply',1000000000,'market_cap',c.price*c.circulation,
     'fdv',c.price*1000000000,'volume_24h',c.volume_24h::double precision/1000000,
     'change_24h',CASE WHEN c.first_price>0 THEN (c.price/c.first_price-1)*100 ELSE 0 END,
     'pool_usd',c.cash::double precision/1000000,'created_at',c.created_at,'progress',c.progress,'stage',c.stage,
     'txns',c.txns,'holders',c.holders,'in_feed',c.rn<=60,'buy_usd_5m',coalesce(s.buys,0),'sell_usd_5m',coalesce(s.sells,0),
     'buyers_5m',coalesce(s.buyers,0),'buys_5m',coalesce(s.buy_count,0),'sells_5m',coalesce(s.sell_count,0),'heat_score',coalesce(s.score,0),
     'windows',(SELECT jsonb_object_agg(w.label,jsonb_build_object(
       'volume',coalesce(ws.volume,0),'txns',coalesce(ws.txns,0),'traders',coalesce(ws.traders,0),
       'buy_usd',coalesce(ws.buys,0),'sell_usd',coalesce(ws.sells,0),'buyers',coalesce(ws.buyers,0),
       'buys',coalesce(ws.buy_count,0),'sells',coalesce(ws.sell_count,0),'heat',coalesce(ws.score,0),
       'change',CASE WHEN b.price>0 THEN (c.price/b.price-1)*100 ELSE NULL END))
       FROM periods w LEFT JOIN stats ws ON ws.label=w.label AND ws.coin=c.id
       LEFT JOIN LATERAL(SELECT coalesce(
         (SELECT price FROM trades WHERE coin=c.id AND ts<=now_s-w.seconds ORDER BY ts DESC,id DESC LIMIT 1),
         (SELECT price FROM trades WHERE coin=c.id AND ts>now_s-w.seconds AND ts<=now_s ORDER BY ts,id LIMIT 1)) AS price) b ON true)) AS value
 FROM candidates c LEFT JOIN stats s ON s.coin=c.id AND s.label='5m'
)
SELECT jsonb_build_object(
 'coins',coalesce((SELECT jsonb_agg(value ORDER BY created_at DESC,id) FROM rendered WHERE rn<=60 OR selected),'[]'),
 'screener',coalesce((SELECT jsonb_agg(value ORDER BY created_at DESC,id) FROM rendered WHERE rn<=60 OR is_hot),'[]'),
 'trending',coalesce((SELECT jsonb_agg(value ORDER BY score DESC,id) FROM (SELECT * FROM rendered WHERE is_hot AND score>0 ORDER BY score DESC,id LIMIT 10) top_coins),'[]'),
 'pulse_counts',jsonb_build_object('new',(SELECT count(*) FROM ranked WHERE stage='new'),
   'stretch',(SELECT count(*) FROM ranked WHERE stage='stretch'),'migrated',(SELECT count(*) FROM ranked WHERE stage='migrated')),
 'total_coins',(SELECT count(*) FROM ranked),
 'market_totals',(SELECT jsonb_object_agg(w.label,jsonb_build_object('volume',coalesce(t.volume,0),'txns',coalesce(t.txns,0)))
   FROM periods w LEFT JOIN(SELECT label,sum(volume) AS volume,sum(txns) AS txns FROM stats GROUP BY label) t ON t.label=w.label))
$$;

CREATE OR REPLACE FUNCTION norx_build_state(now_s bigint,policies jsonb)
RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT norx_coin_data(now_s)||jsonb_build_object(
 'api_version',6,'simulation',jsonb_build_object('running',true,'status','live','last_tick_at',now_s,'age_seconds',0),
 'trades',norx_public_trades(),'large_trades',norx_public_trades(NULL,1000000000,10),'coin_trades','[]'::jsonb,
 'trending_window_seconds',300,'agents',coalesce((SELECT jsonb_agg(jsonb_build_object(
   'id',a.id,'cash',a.cash,'name',p.name,'persona',p.persona,'starting_cash',g.amount,
   'trades',coalesce(t.trades,0),'biggest_buy',coalesce(t.biggest_buy,0),'strategy',policies->p.persona->>1,
   'personality',policies->p.persona->>0,'disciplined',(policies->p.persona->>9)::boolean,
   'risk',(policies->p.persona->>2)::double precision,'patience',(policies->p.persona->>6)::double precision) ORDER BY a.id)
   FROM accounts a JOIN agent_personas p ON p.account=a.id LEFT JOIN agent_grants g ON g.account=a.id
   LEFT JOIN(SELECT account,count(*) AS trades,max(amount) FILTER(WHERE side='buy') AS biggest_buy FROM trades GROUP BY account) t ON t.account=a.id
   WHERE a.kind='agent'),'[]'::jsonb),
 'condition',(SELECT value FROM meta WHERE key='condition'),'simulated',true,
 'next_launch_at',(SELECT value::bigint FROM meta WHERE key='next_launch_at'),'server_time',now_s,'launch_batch',5)
$$;

CREATE OR REPLACE FUNCTION norx_refresh(now_s bigint,visit boolean,scenario jsonb,policies jsonb)
RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE control record; image jsonb;
BEGIN
 IF NOT pg_try_advisory_xact_lock(hashtext('norx-write-'||current_schema())) THEN RETURN false; END IF;
 SELECT active_until,next_batch_at,snapshot IS NOT NULL AS has_snapshot INTO STRICT control FROM cloud_runtime WHERE id=1;
 IF visit THEN
   IF control.active_until<now_s+60 THEN UPDATE cloud_runtime SET active_until=now_s+120 WHERE id=1; END IF;
   IF control.active_until<now_s AND control.has_snapshot THEN UPDATE meta SET value=(now_s+60)::text WHERE key='next_launch_at'; END IF;
 ELSIF control.active_until<now_s THEN RETURN false;
 END IF;
 IF control.next_batch_at>now_s AND control.has_snapshot THEN RETURN true; END IF;
 IF (SELECT value FROM meta WHERE key='simulation_engine') IS DISTINCT FROM 'cloudflare' THEN
   RAISE EXCEPTION 'Activate the Cloudflare simulation using cloudflare/prepare.py --activate' USING ERRCODE='P0001';
 END IF;
 PERFORM norx_batch(now_s,scenario,policies);
 image:=norx_build_state(now_s,policies);
 UPDATE cloud_runtime SET snapshot=image,snapshot_at=now_s,next_batch_at=now_s+10 WHERE id=1;
 RETURN true;
END $$;

CREATE OR REPLACE FUNCTION norx_snapshot(now_s bigint,selected_token text DEFAULT NULL,include_agents boolean DEFAULT false)
RETURNS TABLE(body text,snapshot_at bigint,next_batch_at bigint,active_until bigint)
LANGUAGE plpgsql STABLE AS $$
DECLARE r record; image jsonb; age bigint; extra jsonb; total_agents integer;
BEGIN
 SELECT * INTO STRICT r FROM cloud_runtime WHERE id=1;
 snapshot_at:=r.snapshot_at;next_batch_at:=r.next_batch_at;active_until:=r.active_until;
 IF r.snapshot IS NULL THEN body:=NULL;RETURN NEXT;RETURN; END IF;
 image:=r.snapshot;age:=greatest(0,now_s-r.snapshot_at);
 total_agents:=jsonb_array_length(image->'agents');
 IF NOT include_agents THEN image:=image||jsonb_build_object('agents','[]'::jsonb); END IF;
 image:=image||jsonb_build_object('agent_count',total_agents,'simulation',jsonb_build_object(
   'running',age<=90,'status',CASE WHEN age<=20 THEN 'live' WHEN age<=90 THEN 'delayed' ELSE 'paused' END,
   'last_tick_at',r.snapshot_at,'age_seconds',age),'server_time',now_s);
 IF selected_token IS NOT NULL AND selected_token!='' THEN
   IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(image->'coins') c WHERE c->>'id'=selected_token) THEN
     extra:=norx_coin_data(now_s,selected_token)->'coins'->0;
     IF extra IS NOT NULL THEN image:=jsonb_set(image,'{coins}',(image->'coins')||jsonb_build_array(extra||jsonb_build_object('in_feed',false))); END IF;
   END IF;
   image:=image||jsonb_build_object('coin_trades',norx_public_trades(selected_token,0,50));
 END IF;
 body:=image::text;RETURN NEXT;
END $$;

REVOKE ALL ON FUNCTION norx_policy_label(text),norx_public_trades(text,bigint,integer),
 norx_coin_data(bigint,text),norx_build_state(bigint,jsonb),norx_refresh(bigint,boolean,jsonb,jsonb),norx_snapshot(bigint,text,boolean) FROM PUBLIC;
