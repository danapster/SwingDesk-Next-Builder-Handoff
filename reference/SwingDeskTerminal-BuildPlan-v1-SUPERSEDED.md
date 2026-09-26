# THE SWING DESK TERMINAL
## Complete Build Plan, Concept Knowledge Base & Master Prompt
### Version 1.0 — Full Architecture Document

---

> **For the AI building this app:** Everything in the KNOWLEDGE BASE sections is how you will *see*, *identify*, and *calculate* each concept using raw OHLCV candle data from an MT5 live feed. You are not pattern-matching visually. You are computing mathematically from arrays of candle objects. Read every definition, formula, and detection rule before writing a single line of code.

---

## PART ONE: KNOWLEDGE BASE
### How the App Sees Price — The Candle Object

Every candle from MT5 is an object with the following properties:

```javascript
{
  time: 1714000000,   // Unix timestamp (seconds)
  open: 1.08234,      // Opening price
  high: 1.08890,      // Highest price of the period
  low:  1.08100,      // Lowest price of the period
  close: 1.08750,     // Closing price
  volume: 1842        // Tick volume
}
```

All calculations use arrays of these objects ordered oldest to newest: `candles[0]` is the oldest, `candles[n-1]` is the most recent (current) candle.

Timeframes used: **W1 (Weekly), D1 (Daily), H8 (8-Hour)**

---

## KNOWLEDGE BASE MODULE 1: PO3 — Power of Three Bias Engine

### What PO3 Is

Power of Three is an ICT (Inner Circle Trader) concept describing how institutional money operates in three phases within any given timeframe candle:

1. **Accumulation** — Smart money builds positions at lows (for longs) or highs (for shorts). Price moves sideways in a tight range. Retail traders see "consolidation" and ignore it.
2. **Manipulation** — Price spikes in the *opposite* direction of the intended move. This is the stop hunt. Retail traders get stopped out or enter in the wrong direction.
3. **Distribution** — Price moves aggressively in the true direction to the target. Retail traders who survived the manipulation now chase the move too late.

The PO3 bias engine uses **weekly and daily candle closes relative to previous candle highs and lows** to determine which phase the market is entering.

### The Math: Weekly Bias Calculation

```
Let:
  prev_W  = candles_W1[n-2]   // Previous completed weekly candle
  curr_W  = candles_W1[n-1]   // Current weekly candle (just closed or in progress)

  prev_high = prev_W.high
  prev_low  = prev_W.low
  curr_close = curr_W.close
  curr_high  = curr_W.high
  curr_low   = curr_W.low
```

**Rule 1 — Bullish Weekly Bias:**
```
IF curr_close > prev_high
  → Price closed ABOVE the previous weekly high
  → Bias = BULLISH for the coming week
  → Interpretation: Institutional buying absorbed all sell-side liquidity above prev high
    and committed to higher prices. Next week expect continuation higher.
```

**Rule 2 — Bearish Weekly Bias (High Sweep):**
```
IF curr_high > prev_high AND curr_close < prev_high AND curr_close < prev_W.open
  → Price SWEPT above previous weekly high (taking buy-side liquidity)
    but CLOSED BACK INSIDE the prior weekly range
  → Bias = BEARISH for the coming week
  → Interpretation: Institutions used the breakout to offload long positions onto
    retail breakout buyers. The close back inside is the confirmation of rejection.
    Next week expect a move down.
```

**Rule 3 — Bearish Weekly Bias (Close Below):**
```
IF curr_close < prev_low
  → Price closed BELOW the previous weekly low
  → Bias = BEARISH for the coming week
```

**Rule 4 — Bullish Weekly Bias (Low Sweep):**
```
IF curr_low < prev_low AND curr_close > prev_low AND curr_close > prev_W.open
  → Price SWEPT below previous weekly low (taking sell-side liquidity)
    but CLOSED BACK INSIDE the prior weekly range
  → Bias = BULLISH for the coming week
  → Interpretation: Institutions used the breakdown to accumulate longs from retail
    panic sellers. The reclaim of the prior low is confirmation.
```

**Rule 5 — Neutral / No Bias:**
```
IF curr_close >= prev_low AND curr_close <= prev_high
  AND curr_high <= prev_high AND curr_low >= prev_low
  → Price contained entirely within previous weekly range with no sweep
  → Bias = NEUTRAL — wait for next candle close
```

### The Math: Daily Bias Calculation

Identical logic applied to D1 candles:

```
Let:
  prev_D  = candles_D1[n-2]
  curr_D  = candles_D1[n-1]

Apply same 5 rules substituting D1 candles.
```

Daily bias is *tactical*. Weekly bias is *directional*.

### Confluence Rule:
```
IF weekly_bias == "BULLISH" AND daily_bias == "BULLISH"
  → confluence = "HIGH — Look to BUY during kill zones only"

IF weekly_bias == "BEARISH" AND daily_bias == "BEARISH"
  → confluence = "HIGH — Look to SELL during kill zones only"

IF weekly_bias != daily_bias
  → confluence = "CAUTION — Conflicting bias. Wait for daily realignment."
```

### How the App Displays PO3

For each instrument show:
- A color-coded badge: 🟢 BULLISH / 🔴 BEARISH / 🟡 NEUTRAL
- The specific rule that triggered (e.g. "Weekly High Swept — Bearish")
- The prev weekly high and prev weekly low as key levels
- Confluence status between W and D

---

## KNOWLEDGE BASE MODULE 2: ICT KILL ZONES

### What Kill Zones Are

Kill Zones are specific time windows during the trading day when institutional order flow is highest. Banks and large funds execute the majority of their orders in these windows because liquidity (other traders' orders) is deepest. Price makes its most meaningful directional moves during these windows. Outside of kill zones, price often chops or ranges — stop hunting in both directions.

**All times in EST (Eastern Standard Time / New York Time):**

### The Four Kill Zones

**1. Asian Range (Accumulation Phase)**
```
Time:    20:00 — 00:00 EST (previous evening)
Purpose: Smart money accumulates / distributes quietly
Price:   Usually ranges. The high and low of this session
         become the liquidity pools targeted in London.
Key:     Asian High and Asian Low are critical levels.
         Mark them. They will be swept before or during London KZ.
```

**2. London Kill Zone (Primary Manipulation + Distribution)**
```
Time:    02:00 — 05:00 EST
Purpose: Highest liquidity window. The true directional move of the day
         often begins here.
Behavior: Price will sweep Asian session high or low first
          (the manipulation), then reverse and distribute in
          the true direction.
Trade:   After the sweep and rejection, enter in the direction
         of the daily PO3 bias.
```

**3. New York Kill Zone (Continuation or Reversal)**
```
Time:    08:30 — 11:00 EST
Purpose: Second highest liquidity window. Either continues
         the London move or reverses it (creating a daily
         distribution in the opposite direction).
The 08:30 open is the most volatile minute of the day.
         High-impact US news (CPI, NFP, FOMC) drops at 08:30.
         Never hold a naked position into 08:30 on news days.
```

**4. London Close (Profit Taking)**
```
Time:    10:00 — 12:00 EST
Purpose: London banks close their books. They take profit
         on positions opened in the London KZ.
Behavior: Fade the prior move. If London ran up, London Close
          often pulls price back.
Trade:   Counter-trend scalps only. Lower probability.
```

### Kill Zone Math (How App Detects Active Window)

```javascript
function getActiveKillZone(currentUTCTime) {
  // Convert UTC to EST (UTC-5, or UTC-4 during DST)
  const est = convertToEST(currentUTCTime);
  const hour = est.getHours();
  const min  = est.getMinutes();
  const timeDecimal = hour + (min / 60);

  if (timeDecimal >= 20 || timeDecimal < 0)  return "ASIAN_RANGE";
  if (timeDecimal >= 2  && timeDecimal < 5)  return "LONDON_KZ";
  if (timeDecimal >= 8.5 && timeDecimal < 11) return "NEW_YORK_KZ";
  if (timeDecimal >= 10 && timeDecimal < 12) return "LONDON_CLOSE";
  return "NO_KILL_ZONE";
}
```

### Kill Zone + Bias Integration

```
IF active_kill_zone == "LONDON_KZ" OR "NEW_YORK_KZ"
  AND po3_confluence == "HIGH BULLISH"
  → Look for BUY setups: demand zones, bullish OBs, FVGs in discount
  → Any sweep of a recent low during this window = entry trigger

IF active_kill_zone == "LONDON_KZ" OR "NEW_YORK_KZ"
  AND po3_confluence == "HIGH BEARISH"
  → Look for SELL setups: supply zones, bearish OBs, FVGs in premium
  → Any sweep of a recent high during this window = entry trigger
```

---

## KNOWLEDGE BASE MODULE 3: SUPPLY & DEMAND ZONE ENGINE

### What Supply and Demand Zones Are

Supply and Demand zones are price areas where institutional orders are resting in the market. They are not drawn arbitrarily — they are identified by the *result* of what price did when it left that area. If price left an area explosively and never came back, there are unfilled institutional orders still sitting there. When price returns to that area, those orders activate and cause a reaction.

**Demand Zone**: An area where institutional BUY orders are resting. Price exploded upward from here.
**Supply Zone**: An area where institutional SELL orders are resting. Price collapsed downward from here.

### The Math: Detecting a Base

A "base" is 1-3 candles of consolidation (small bodies, small range) before a strong impulsive move. This is where the orders were placed.

```javascript
function isBaseCandle(candle) {
  const body = Math.abs(candle.close - candle.open);
  const range = candle.high - candle.low;
  const bodyRatio = body / range;
  // A base candle has a small body relative to its range
  return bodyRatio < 0.4 && range < avgRange * 0.6;
  // avgRange = average candle range over last 20 candles
}
```

### The Math: Detecting an Impulsive Move

```javascript
function isImpulsiveMove(candles, startIndex, direction) {
  // Look at the next 3 candles after the base
  let impulseCandles = candles.slice(startIndex, startIndex + 3);
  let totalMove = 0;
  let allInDirection = true;

  for (let c of impulseCandles) {
    let body = c.close - c.open;
    if (direction === "UP" && body < 0) allInDirection = false;
    if (direction === "DOWN" && body > 0) allInDirection = false;
    totalMove += Math.abs(body);
  }

  // Impulsive = total move is more than 1.5x average range
  // AND most candles close in the direction
  return totalMove > (avgRange * 1.5) && allInDirection;
}
```

### The Math: Defining Zone Boundaries

```javascript
function createDemandZone(baseCandles) {
  // Demand zone boundaries = the base candle(s) before the bullish impulse
  const proximal = Math.max(...baseCandles.map(c => c.close)); // Highest close of base
  const distal   = Math.min(...baseCandles.map(c => c.low));   // Lowest low of base
  return { proximal, distal, type: "DEMAND" };
}

function createSupplyZone(baseCandles) {
  // Supply zone boundaries = the base candle(s) before the bearish impulse
  const proximal = Math.min(...baseCandles.map(c => c.close)); // Lowest close of base
  const distal   = Math.max(...baseCandles.map(c => c.high));  // Highest high of base
  return { proximal, distal, type: "SUPPLY" };
}
```

### Zone Strength Validation — The Critical Filter

A zone is only tagged STRONG if the move away from it **broke a prior opposing zone or structure**. This is what makes it institutional — they had enough orders to overcome the opposition on the other side.

```javascript
function validateZoneStrength(zone, allZones, candles) {
  // Find the impulse that left this zone
  // Check if that impulse broke through the nearest opposing zone

  const opposingZones = allZones.filter(z =>
    z.type !== zone.type &&
    (zone.type === "DEMAND" ? z.proximal > zone.proximal : z.proximal < zone.proximal)
  );

  if (opposingZones.length === 0) return "STRONG"; // No opposition = clearly strong

  const nearestOpposing = opposingZones.sort((a, b) =>
    Math.abs(a.proximal - zone.proximal) - Math.abs(b.proximal - zone.proximal)
  )[0];

  // Did the impulse from our zone close candles THROUGH the opposing zone?
  const impulseCandles = getImpulseCandles(zone, candles);
  const broke = impulseCandles.some(c =>
    zone.type === "DEMAND"
      ? c.close > nearestOpposing.distal   // Bullish impulse broke through supply
      : c.close < nearestOpposing.distal   // Bearish impulse broke through demand
  );

  return broke ? "STRONG" : "WEAK";
}
```

### Zone Tags and Rules

```
PRISTINE  → Fresh (never retested) + STRONG + aligned with HTF zone of same type
STRONG    → Impulse broke opposing structure/zone
TESTED    → Price has returned to the zone at least once and reacted
            (second test is lower probability than first)
WEAK      → Impulse did NOT break opposing structure
INVALID   → Price has traded THROUGH the zone without reacting
            (remove from dashboard)
```

### Timeframe Hierarchy for Zones

```
W1 zone > D1 zone > H8 zone

A D1 demand zone sitting INSIDE a W1 demand zone = PREMIUM quality setup.
The app must check for this nesting and tag accordingly.

If W1 = SUPPLY zone but D1 = DEMAND zone in same area:
→ Flag as CONFLICTING ZONES — caution, wait for resolution
```

---

## KNOWLEDGE BASE MODULE 4: ICT CONCEPTS — FVG, iFVG, ORDER BLOCKS

### 4A: Fair Value Gap (FVG)

### What an FVG Is

A Fair Value Gap is an imbalance in price where one side of the market (buyers or sellers) completely dominated and left a gap in the two-sided price auction. It appears as a 3-candle pattern where the wicks of candles 1 and 3 do not overlap. This gap represents an area where price never traded — meaning buy and sell orders were never matched there. Institutions will often return price to this area to fill orders left behind.

### The Math: Detecting a Bullish FVG

```javascript
function detectBullishFVG(candles, i) {
  // Three candle pattern: candle[i-2], candle[i-1], candle[i]
  const c1 = candles[i-2];  // First candle
  const c2 = candles[i-1];  // Middle candle (the impulse)
  const c3 = candles[i];    // Third candle

  // Bullish FVG: gap between C1 low and C3 high
  // C1.low must be HIGHER than C3.high — gap exists between them
  // Wait — correct ICT definition:
  // Bullish FVG = C1.high < C3.low (gap between top of C1 and bottom of C3)

  if (c3.low > c1.high && c2.close > c2.open) {
    return {
      type: "BULLISH_FVG",
      top: c3.low,          // Upper boundary of the FVG
      bottom: c1.high,      // Lower boundary of the FVG
      midpoint: (c3.low + c1.high) / 2,  // 50% level — key reaction area
      formed_at: c3.time,
      filled: false
    };
  }
  return null;
}
```

### The Math: Detecting a Bearish FVG

```javascript
function detectBearishFVG(candles, i) {
  const c1 = candles[i-2];
  const c2 = candles[i-1];
  const c3 = candles[i];

  // Bearish FVG = C1.low > C3.high (gap between bottom of C1 and top of C3)
  if (c1.low > c3.high && c2.close < c2.open) {
    return {
      type: "BEARISH_FVG",
      top: c1.low,          // Upper boundary
      bottom: c3.high,      // Lower boundary
      midpoint: (c1.low + c3.high) / 2,
      formed_at: c3.time,
      filled: false
    };
  }
  return null;
}
```

### FVG Fill Logic

```javascript
function checkFVGFill(fvg, subsequentCandles) {
  for (let c of subsequentCandles) {
    if (fvg.type === "BULLISH_FVG") {
      // Filled when price trades back down into the gap
      if (c.low <= fvg.midpoint) {
        fvg.filled = true;
        fvg.fill_time = c.time;
      }
    }
    if (fvg.type === "BEARISH_FVG") {
      // Filled when price trades back up into the gap
      if (c.high >= fvg.midpoint) {
        fvg.filled = true;
        fvg.fill_time = c.time;
      }
    }
  }
}
```

---

### 4B: Inverse Fair Value Gap (iFVG)

### What an iFVG Is

When price returns to a Bullish FVG and FILLS it (trades through the midpoint), the FVG is consumed. But the area it occupied now flips polarity. A filled Bullish FVG becomes a **Bearish iFVG** — a resistance area. A filled Bearish FVG becomes a **Bullish iFVG** — a support area. This is because institutional orders that were resting there have now been activated, and the residual flow from that activation creates a reaction on the next visit.

```javascript
function convertToIFVG(fvg) {
  if (fvg.filled) {
    return {
      type: fvg.type === "BULLISH_FVG" ? "BEARISH_IFVG" : "BULLISH_IFVG",
      top: fvg.top,
      bottom: fvg.bottom,
      midpoint: fvg.midpoint,
      original_type: fvg.type,
      converted_at: fvg.fill_time
    };
  }
}
```

---

### 4C: Order Blocks (OB)

### What an Order Block Is

An Order Block is the last candle (or small group of candles) moving in the *opposite* direction before a significant institutional impulse move. It represents the candle where institutions were placing their orders in bulk. When price returns to this area, those same institutions defend their positions, causing a strong reaction.

**Bullish OB**: The last DOWN candle (red/bearish candle) before a significant bullish impulse move.
**Bearish OB**: The last UP candle (green/bullish candle) before a significant bearish impulse move.

### The Math: Detecting a Bullish Order Block

```javascript
function detectBullishOB(candles, i) {
  // Look for: last bearish candle before a bullish impulse
  // Significant impulse = next 2-3 candles move up more than 1.5x avgRange

  const candidate = candles[i];

  // Candidate must be bearish
  if (candidate.close >= candidate.open) return null;

  // Check if followed by strong bullish move
  const next3 = candles.slice(i+1, i+4);
  const totalUp = next3.reduce((sum, c) => sum + Math.max(0, c.close - c.open), 0);

  if (totalUp > avgRange * 1.5) {
    return {
      type: "BULLISH_OB",
      top: candidate.high,     // Upper boundary of OB
      bottom: candidate.low,   // Lower boundary of OB
      ob_open: candidate.open,
      ob_close: candidate.close,
      // The most important levels: OB body (open to close of the bearish candle)
      body_top: Math.max(candidate.open, candidate.close),
      body_bottom: Math.min(candidate.open, candidate.close),
      formed_at: candidate.time,
      mitigated: false
    };
  }
  return null;
}
```

### The Math: Detecting a Bearish Order Block

```javascript
function detectBearishOB(candles, i) {
  const candidate = candles[i];

  // Candidate must be bullish
  if (candidate.close <= candidate.open) return null;

  // Check if followed by strong bearish move
  const next3 = candles.slice(i+1, i+4);
  const totalDown = next3.reduce((sum, c) => sum + Math.max(0, c.open - c.close), 0);

  if (totalDown > avgRange * 1.5) {
    return {
      type: "BEARISH_OB",
      top: candidate.high,
      bottom: candidate.low,
      body_top: Math.max(candidate.open, candidate.close),
      body_bottom: Math.min(candidate.open, candidate.close),
      formed_at: candidate.time,
      mitigated: false
    };
  }
  return null;
}
```

### OB Mitigation

An OB is mitigated (consumed) when price trades back into the OB body:

```javascript
function checkOBMitigation(ob, subsequentCandles) {
  for (let c of subsequentCandles) {
    if (ob.type === "BULLISH_OB") {
      // Mitigated when price trades into the OB body from above
      if (c.low <= ob.body_top && c.low >= ob.body_bottom) {
        ob.mitigated = true;
        ob.mitigation_time = c.time;
      }
    }
    if (ob.type === "BEARISH_OB") {
      // Mitigated when price trades into the OB body from below
      if (c.high >= ob.body_bottom && c.high <= ob.body_top) {
        ob.mitigated = true;
        ob.mitigation_time = c.time;
      }
    }
  }
}
```

### 4D: Breaker Block

When an Order Block is violated — meaning price trades completely through it without reacting — it becomes a Breaker Block. It now acts as an obstacle in the opposite direction.

```javascript
function detectBreakerBlock(ob, subsequentCandles) {
  for (let c of subsequentCandles) {
    if (ob.type === "BULLISH_OB") {
      // Bullish OB becomes Bearish Breaker when price closes below OB bottom
      if (c.close < ob.bottom) {
        return {
          type: "BEARISH_BREAKER",
          top: ob.top,
          bottom: ob.bottom,
          original_ob: ob,
          broken_at: c.time
        };
      }
    }
    if (ob.type === "BEARISH_OB") {
      // Bearish OB becomes Bullish Breaker when price closes above OB top
      if (c.close > ob.top) {
        return {
          type: "BULLISH_BREAKER",
          top: ob.top,
          bottom: ob.bottom,
          original_ob: ob,
          broken_at: c.time
        };
      }
    }
  }
}
```

### 4E: Mitigation Block

A Mitigation Block is an OB where price has partially entered the zone (touched the body) but has NOT fully traded through. It has been partially filled — like a half-loaded spring. On the next visit it tends to have a high-probability reaction because some (but not all) orders were activated.

```javascript
function detectMitigationBlock(ob, subsequentCandles) {
  // Price entered OB body but did NOT close through the opposite side
  for (let c of subsequentCandles) {
    if (ob.type === "BULLISH_OB") {
      const enteredBody = c.low <= ob.body_top && c.low >= ob.body_bottom;
      const didNotBreak = c.close > ob.bottom;
      if (enteredBody && didNotBreak) {
        ob.is_mitigation_block = true;
        ob.mitigation_entry_time = c.time;
      }
    }
  }
}
```

---

## KNOWLEDGE BASE MODULE 5: THE 71% FIBONACCI SETUP

### What the 71% Setup Is

The 71% Fibonacci retracement setup (also called OTE — Optimal Trade Entry in ICT methodology) is a precision entry model. After a significant impulse move, price retraces to the 61.8%–78.6% zone before continuing in the original direction. The sweet spot is the 70.5%–71% level — the zone where institutional limit orders to re-enter are resting.

The logic: institutions make the impulse move, then allow retail to "chase" the move as it pulls back. While retail sells the pullback (in a bull move), institutions are placing buy limit orders at the 71% retracement. When enough orders are accumulated, price reverses sharply.

### The Math: Fibonacci Level Calculation

```javascript
function calculateFibLevels(swingHigh, swingLow, direction) {
  // direction: "BULLISH" = measuring retracement after bullish impulse
  //            "BEARISH" = measuring retracement after bearish impulse

  const range = swingHigh - swingLow;

  const levels = {
    0:     direction === "BULLISH" ? swingHigh : swingLow,
    23.6:  direction === "BULLISH"
             ? swingHigh - (range * 0.236)
             : swingLow  + (range * 0.236),
    38.2:  direction === "BULLISH"
             ? swingHigh - (range * 0.382)
             : swingLow  + (range * 0.382),
    50.0:  direction === "BULLISH"
             ? swingHigh - (range * 0.500)
             : swingLow  + (range * 0.500),
    61.8:  direction === "BULLISH"
             ? swingHigh - (range * 0.618)
             : swingLow  + (range * 0.618),
    70.5:  direction === "BULLISH"
             ? swingHigh - (range * 0.705)
             : swingLow  + (range * 0.705),
    71.0:  direction === "BULLISH"
             ? swingHigh - (range * 0.710)
             : swingLow  + (range * 0.710),  // PRIMARY ENTRY
    78.6:  direction === "BULLISH"
             ? swingHigh - (range * 0.786)
             : swingLow  + (range * 0.786),
    100:   direction === "BULLISH" ? swingLow : swingHigh
  };

  // OTE Zone: between 61.8% and 78.6%
  levels.OTE_top    = levels[61.8];
  levels.OTE_bottom = levels[78.6];
  levels.primary_entry = levels[71.0];

  return levels;
}
```

### The Math: Detecting a 71% Setup

```javascript
function detect71Setup(candles, fibLevels, direction) {
  const currentCandle = candles[candles.length - 1];
  const currentPrice = currentCandle.close;

  const inOTEZone = direction === "BULLISH"
    ? currentPrice <= fibLevels[61.8] && currentPrice >= fibLevels[78.6]
    : currentPrice >= fibLevels[61.8] && currentPrice <= fibLevels[78.6];

  const atPrimaryEntry = direction === "BULLISH"
    ? currentPrice <= fibLevels[71.0] * 1.001 && currentPrice >= fibLevels[71.0] * 0.999
    : currentPrice >= fibLevels[71.0] * 0.999 && currentPrice <= fibLevels[71.0] * 1.001;

  return {
    in_ote_zone: inOTEZone,
    at_primary_entry: atPrimaryEntry,
    nearest_fib: findNearestFibLevel(currentPrice, fibLevels),
    distance_to_primary: Math.abs(currentPrice - fibLevels[71.0])
  };
}
```

### Confluence Scoring for 71% Setup

```javascript
function score71Setup(fibSetup, killZone, nearbyOB, nearbyFVG, nearbySDZone, po3Bias, macroBias) {
  let score = 0;
  let reasons = [];

  if (killZone !== "NO_KILL_ZONE") {
    score++;
    reasons.push("Kill Zone active");
  }
  if (nearbyOB && Math.abs(nearbyOB.body_top - fibSetup.primary_entry) < spread * 5) {
    score++;
    reasons.push("OB at 71% level");
  }
  if (nearbyFVG && fibSetup.primary_entry >= nearbyFVG.bottom && fibSetup.primary_entry <= nearbyFVG.top) {
    score++;
    reasons.push("FVG at 71% level");
  }
  if (nearbySDZone) {
    score++;
    reasons.push("S&D zone confluence");
  }
  if (po3Bias.weekly === po3Bias.daily) {
    score++;
    reasons.push("PO3 W+D aligned");
  }

  return {
    score,
    max: 5,
    reasons,
    recommendation: score >= 4 ? "TAKE SETUP" : score >= 3 ? "WATCH" : "SKIP"
  };
}
```

---

## KNOWLEDGE BASE MODULE 6: SUPPLY & DEMAND — MEASURED MOVE ENGINE

### What a Measured Move Is

When price breaks out of a consolidation or supply/demand zone, the expected move distance equals the height of the zone or consolidation it just broke from. This is the "measured move" projection.

### The Math

```javascript
function calculateMeasuredMove(zone, breakoutCandle) {
  const zoneHeight = zone.distal - zone.proximal;

  if (zone.type === "DEMAND") {
    // Bullish breakout: target is breakout level + zone height
    const breakoutLevel = zone.proximal;
    const target = breakoutLevel + zoneHeight;
    const pipTarget = (target - breakoutCandle.close) / pipValue;
    return { target, pipTarget, direction: "UP" };
  }

  if (zone.type === "SUPPLY") {
    // Bearish breakout: target is breakout level - zone height
    const breakoutLevel = zone.proximal;
    const target = breakoutLevel - zoneHeight;
    const pipTarget = (breakoutCandle.close - target) / pipValue;
    return { target, pipTarget, direction: "DOWN" };
  }
}
```

### Liquidity Target Mapping

```javascript
function mapLiquidityTargets(candles_W1, candles_D1, currentPrice) {
  const prevWeekHigh = candles_W1[candles_W1.length - 2].high;
  const prevWeekLow  = candles_W1[candles_W1.length - 2].low;
  const prevDayHigh  = candles_D1[candles_D1.length - 2].high;
  const prevDayLow   = candles_D1[candles_D1.length - 2].low;

  // Equal highs/lows: find two or more swing highs within 5 pips of each other
  const equalHighs = findEqualLevels(candles_D1, "highs", 5);
  const equalLows  = findEqualLevels(candles_D1, "lows", 5);

  return {
    buy_side_liquidity:  [prevWeekHigh, prevDayHigh, ...equalHighs],
    sell_side_liquidity: [prevWeekLow,  prevDayLow,  ...equalLows],
    // Price targets the nearest liquidity pool in the bias direction
  };
}
```

---

## KNOWLEDGE BASE MODULE 7: PD ARRAY (PREMIUM / DISCOUNT)

### What PD Array Is

The Premium/Discount array is ICT's framework for knowing if you are buying cheap or selling expensive within any range.

```javascript
function calculatePDArray(rangeHigh, rangeLow) {
  const range = rangeHigh - rangeLow;
  const equilibrium = rangeLow + (range * 0.50);

  return {
    equilibrium,
    premium_zone:  { top: rangeHigh,          bottom: equilibrium },
    discount_zone: { top: equilibrium,         bottom: rangeLow },
    // ICT levels within the array:
    buyside_1:   rangeLow  + (range * 0.00),  // Range low
    optimal_1:   rangeLow  + (range * 0.236),
    optimal_2:   rangeLow  + (range * 0.382),
    fair_value:  equilibrium,
    optimal_3:   rangeLow  + (range * 0.618),
    optimal_4:   rangeLow  + (range * 0.705), // OTE bottom
    optimal_5:   rangeLow  + (range * 0.786), // OTE top
    sellside_1:  rangeHigh
  };
}

// Rule:
// BUY in discount zone (price below equilibrium) — you are buying cheap
// SELL in premium zone (price above equilibrium) — you are selling expensive
// Never buy in premium, never sell in discount (against institution logic)
```

---

## KNOWLEDGE BASE MODULE 8: RISK ENGINE

### Position Size Calculation

```javascript
function calculatePositionSize(accountBalance, riskPercent, entryPrice, stopLossPrice, instrument) {
  const riskAmount  = accountBalance * (riskPercent / 100);
  const pipRisk     = Math.abs(entryPrice - stopLossPrice) / pipValue[instrument];
  const pipValue_$  = pipValueInDollars[instrument]; // e.g. $10 per pip for standard lot on EURUSD
  const lotSize     = riskAmount / (pipRisk * pipValue_$);

  return {
    riskAmount,      // Dollar amount being risked
    pipRisk,         // Pips to stop loss
    lotSize: Math.floor(lotSize * 100) / 100,  // Round down to nearest 0.01
    rewardTarget_1R: entryPrice + (entryPrice - stopLossPrice) * 1,
    rewardTarget_2R: entryPrice + (entryPrice - stopLossPrice) * 2,
    rewardTarget_3R: entryPrice + (entryPrice - stopLossPrice) * 3,
  };
}
```

### Pre-Flight Checklist Logic

```javascript
function runPreFlightCheck(trade, context) {
  const checks = [
    {
      id: "bias",
      label: "PO3 Bias Confirmed",
      pass: context.po3.confluence === "HIGH" &&
            context.po3.direction === trade.direction,
      fail_reason: "Weekly and Daily bias not aligned or conflicts with trade direction"
    },
    {
      id: "killzone",
      label: "Kill Zone Active",
      pass: context.killZone !== "NO_KILL_ZONE",
      fail_reason: "No active kill zone — wait for London or NY session"
    },
    {
      id: "zone",
      label: "Entry Zone Validated",
      pass: context.nearestZone &&
            context.nearestZone.strength === "STRONG" ||
            context.nearestOB !== null ||
            context.nearestFVG !== null,
      fail_reason: "No validated OB, FVG, or Strong S&D zone at entry"
    },
    {
      id: "fib",
      label: "OTE Zone Confluence",
      pass: context.fibSetup && context.fibSetup.in_ote_zone,
      fail_reason: "Price not in 61.8–78.6% OTE zone"
    },
    {
      id: "risk",
      label: "Risk Within Limit",
      pass: trade.riskPercent <= 2.0,
      fail_reason: "Risk exceeds 2% hard cap — reduce position size"
    },
    {
      id: "news",
      label: "No High-Impact News Within 30 Min",
      pass: !context.upcomingNews.highImpact,
      fail_reason: `High-impact event in ${context.upcomingNews.minutesAway} minutes`
    },
    {
      id: "rr",
      label: "Minimum 3:1 Reward-to-Risk",
      pass: trade.rewardToRisk >= 3.0,
      fail_reason: `Current RR is ${trade.rewardToRisk.toFixed(1)} — minimum 3:1 required`
    }
  ];

  const failed = checks.filter(c => !c.pass);
  const passed = checks.filter(c => c.pass);

  return {
    all_passed: failed.length === 0,
    passed_count: passed.length,
    total_checks: checks.length,
    failed_checks: failed,
    block_order: failed.length > 0
  };
}
```

---

## PART TWO: FULL APP ARCHITECTURE

### Component Inventory

| # | Module | Sub-Components | Priority |
|---|--------|---------------|----------|
| 1 | Macro Intelligence Layer | CB Stance, Rate Differential, DXY Meter, Eco Calendar | HIGH |
| 2 | PO3 Bias Engine | Weekly Bias, Daily Bias, Confluence Score | CRITICAL |
| 3 | S&D Zone Engine | Zone Detection, Strength Validator, Zone Dashboard, Chart Draw | CRITICAL |
| 4 | ICT Engine | FVG Scanner, iFVG Tracker, OB Engine, Breaker/Mitigation, Kill Zone Timers | CRITICAL |
| 5 | 71% Fib Engine | Fib Calculator, Setup Validator, Confluence Scorer | HIGH |
| 6 | Execution Layer | Pre-Flight Checker, Risk Engine, Order Types, Trade Management, Alerts, Bulk Ops | HIGH |
| 7 | Measured Move Engine | Structure Projection, Liquidity Mapper, PD Array | HIGH |
| 8 | Dashboard UI | Terminal View, War Room, Open Trades, Charts, Weekly Briefing | CRITICAL |

**Total: 8 Modules | 34 Sub-Components | 6 Calculation Engines | 4 Execution Layers**

---

## PART THREE: BUILD SEQUENCE

Build in this exact order so you always have a working app at each stage:

```
STAGE 1 — Shell & Navigation
  → Dark terminal UI, sidebar nav, instrument selector, responsive layout

STAGE 2 — MT5 Price Feed Integration
  → WebSocket connection to MT5, live OHLCV per instrument, price display

STAGE 3 — PO3 Bias Engine (the brain)
  → Weekly and daily bias calculation, bias cards, confluence scoring

STAGE 4 — Kill Zone Countdowns
  → Active session detection, countdown timers, bias overlay per zone

STAGE 5 — S&D Zone Engine
  → Zone detection on H8/D1/W1, strength validation, zone dashboard table

STAGE 6 — ICT Concepts Engine
  → FVG detection, iFVG conversion, OB detection, Breaker/Mitigation blocks

STAGE 7 — 71% Fib Engine
  → Fib level calculator, OTE zone display, confluence scorer

STAGE 8 — Pre-Flight + Risk Engine
  → Checklist system, position size calculator, order blocker

STAGE 9 — Order Execution Layer
  → Market/limit/stop orders, pending orders, broker integration

STAGE 10 — Trade Management
  → BE automation, trailing stop, partial close, live P&L

STAGE 11 — Measured Move + PD Array
  → Projection tool, liquidity targets, PD array overlay

STAGE 12 — Macro Intelligence Layer
  → CB stance tracker, rate differentials, economic calendar

STAGE 13 — Chart Integration
  → Lightweight-charts embed, zones drawn, OBs/FVGs plotted, Kill Zone shading

STAGE 14 — Weekly Briefing Generator
  → Auto-generated Sunday prep report

STAGE 15 — Bulk Operations + Alerts
  → Multi-trade management, price alerts, push notifications

STAGE 16 — Polish
  → Animations, transitions, mobile responsiveness, performance optimization
```

---

## PART FOUR: THE MASTER BUILD PROMPT

> Copy everything below this line and paste it as your first message to Claude, Cursor, Bolt, or any AI code builder.

---

```
BUILD: THE SWING DESK TERMINAL

You are building a professional swing trading web application called
"The Swing Desk Terminal" as a single self-contained HTML file.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TECH STACK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- HTML5 + Vanilla JavaScript (no React, no Vue — keep it portable)
- Tailwind CSS via Play CDN
- lightweight-charts v4 by TradingView (via CDN) for charts
- Chart.js (via CDN) for dashboard analytics
- Inter font from Google Fonts
- localStorage for all persistence
- MT5 WebSocket for live price feed (user provides server URL)
- Alpha Vantage free API or Yahoo Finance for OHLCV history
- FRED API for macro data (no key needed for basic endpoints)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VISUAL DESIGN — NON-NEGOTIABLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Background:        #0A0A0F (near-black)
Surface cards:     #111118 with 1px border #1E1E2E
Primary accent:    #3B82F6 (electric blue)
Secondary accent:  #F59E0B (gold)
Bullish green:     #10B981
Bearish red:       #EF4444
Text primary:      #F1F5F9
Text muted:        #64748B
Font:              Inter (weights 300, 400, 500, 600, 700)
Card style:        Subtle glassmorphism — backdrop-filter blur(8px),
                   background rgba(17,17,24,0.8), border 1px solid
                   rgba(255,255,255,0.06)
This must look like a $500/month professional trading terminal.
Every pixel must feel intentional. No Bootstrap defaults. No gray boxes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW YOU SEE PRICE — THE CANDLE OBJECT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Every candle from MT5 is: { time, open, high, low, close, volume }
Candles are arrays ordered oldest[0] to newest[n-1].
Timeframes: W1, D1, H8.
ALL calculations below use raw OHLCV math — not visual pattern matching.
avgRange = average of (high - low) over last 20 candles of that timeframe.
pipValue per instrument: EURUSD/GBPUSD = 0.0001, JPY pairs = 0.01,
XAUUSD = 0.01, US30/NAS100 = 1.0.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODULE 1 — PO3 BIAS ENGINE (Power of Three)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCEPT: Price moves in 3 phases — Accumulation, Manipulation, Distribution.
The bias engine reads the most recent weekly and daily candle closes to
determine institutional direction for the coming period.

WEEKLY BIAS RULES (apply to W1 candles, prev = candles_W1[n-2], curr = candles_W1[n-1]):

  BULLISH:  curr.close > prev.high
            → Closed above prev weekly high. Bullish next week.

  BEARISH (sweep high):
            curr.high > prev.high
            AND curr.close < prev.high
            AND curr.close < prev.open
            → Swept prev high, closed back inside. Bearish next week.

  BEARISH:  curr.close < prev.low
            → Closed below prev weekly low. Bearish next week.

  BULLISH (sweep low):
            curr.low < prev.low
            AND curr.close > prev.low
            AND curr.close > prev.open
            → Swept prev low, closed back inside. Bullish next week.

  NEUTRAL:  price contained within prev range, no sweep.

Apply identical logic to D1 candles for daily bias.

CONFLUENCE:
  Weekly == Daily direction → HIGH CONFLUENCE (trade in that direction during kill zones)
  Weekly != Daily direction → CAUTION (wait for daily realignment)

DISPLAY: Color-coded bias card per instrument.
  Show: bias label, triggering rule, prev high/low levels, confluence status.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODULE 2 — ICT KILL ZONES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCEPT: Time windows when institutional order flow is highest.
Only look for entries INSIDE these windows. Outside = no trade.

All times EST:
  Asian Range:     20:00 – 00:00 (mark Asian high/low as liquidity)
  London Kill Zone: 02:00 – 05:00 (primary — highest probability)
  New York Kill Zone: 08:30 – 11:00 (secondary — continuation or reversal)
  London Close:    10:00 – 12:00 (fade/profit-taking only)

DETECTION CODE:
  const est = convertToEST(Date.now());
  const h = est.getHours() + est.getMinutes()/60;
  active zone = h>=20||h<0 → ASIAN; h>=2&&h<5 → LONDON_KZ;
                h>=8.5&&h<11 → NY_KZ; h>=10&&h<12 → LONDON_CLOSE

During LONDON_KZ and NY_KZ:
  IF po3 = BULLISH → look for buy setups (demand zones, bullish OBs, FVGs in discount)
  IF po3 = BEARISH → look for sell setups (supply zones, bearish OBs, FVGs in premium)

DISPLAY: Four zone cards with live countdown timers.
  Active zone pulses with accent color.
  Show PO3 bias direction overlay: "Looking to BUY" or "Looking to SELL"
  Show nearest OB or FVG in the bias direction within each active zone.
  Asian high and low marked and displayed as key levels.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODULE 3 — SUPPLY & DEMAND ZONE ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCEPT: Price areas where institutional orders rest. Identified by the
RESULT of what price did when it left — explosive moves mean unfilled orders remain.

BASE CANDLE DETECTION:
  body = |close - open|; range = high - low
  isBase = (body/range < 0.4) AND (range < avgRange * 0.6)

IMPULSIVE MOVE DETECTION (after the base):
  3 candles after base: totalMove = sum of |close-open|
  isImpulsive = totalMove > avgRange * 1.5 AND majority close in same direction

DEMAND ZONE (bullish):
  proximal = max(close) of base candles
  distal   = min(low)   of base candles
  (price exploded UP from this area)

SUPPLY ZONE (bearish):
  proximal = min(close) of base candles
  distal   = max(high)  of base candles
  (price collapsed DOWN from this area)

STRENGTH VALIDATION (critical — only STRONG zones are traded):
  Find nearest opposing zone in the direction of the impulse.
  If impulse candles closed THROUGH that opposing zone → STRONG
  If impulse did NOT break opposing zone → WEAK
  WEAK zones are shown on dashboard but marked grey — not traded.

ZONE TAGS:
  PRISTINE:  Fresh (never retested) + STRONG + nested inside same-direction HTF zone
  STRONG:    Impulse broke opposing structure
  TESTED:    Price has returned once — still tradeable but lower probability
  WEAK:      Did not break opposing structure — display only, no alerts
  INVALID:   Price traded through without reaction — remove from dashboard

TIMEFRAME HIERARCHY:
  Scan W1, D1, H8 separately. W1 zones override D1. D1 override H8.
  Flag zones where D1 demand is inside W1 demand → PREMIUM tag.
  Flag conflicting zones (W1 supply + D1 demand same area) → CONFLICT tag.

DISPLAY: Zone dashboard table per instrument.
  Columns: Type | Tag | Timeframe | Proximal | Distal | Distance (pips) | Age | Score
  Draw zones on chart as semi-transparent filled rectangles:
    Demand = rgba(16,185,129,0.15) with green border
    Supply = rgba(239,68,68,0.15) with red border
  Proximal line = solid, Distal line = dashed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODULE 4 — ICT CONCEPTS ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

--- FVG (FAIR VALUE GAP) ---
CONCEPT: 3-candle imbalance. Candles 1 and 3 wicks don't overlap.
An area where price never traded — orders weren't matched here.
Institutions return price here to fill those orders.

BULLISH FVG: c3.low > c1.high AND c2 is bullish
  top = c3.low, bottom = c1.high, midpoint = (top+bottom)/2
  Fill check: subsequent candle low <= midpoint → FVG filled

BEARISH FVG: c1.low > c3.high AND c2 is bearish
  top = c1.low, bottom = c3.high, midpoint = (top+bottom)/2
  Fill check: subsequent candle high >= midpoint → FVG filled

--- iFVG (INVERSE FVG) ---
CONCEPT: A filled FVG flips polarity and becomes a reaction zone.
Filled Bullish FVG → Bearish iFVG (resistance)
Filled Bearish FVG → Bullish iFVG (support)
Track all filled FVGs and convert to iFVGs automatically.

--- ORDER BLOCK (OB) ---
CONCEPT: Last opposing candle before significant institutional impulse.
Where the bulk orders were placed. Price returns here to activate
remaining orders — causing a reaction.

BULLISH OB: Last bearish candle before bullish impulse (>1.5x avgRange next 3 candles)
  top = candidate.high, bottom = candidate.low
  body_top = max(open,close), body_bottom = min(open,close)
  Entry: at body_top on retest (discount entry into OB body)

BEARISH OB: Last bullish candle before bearish impulse
  top = candidate.high, bottom = candidate.low
  body_top = max(open,close), body_bottom = min(open,close)
  Entry: at body_bottom on retest

MITIGATION: Price enters OB body but does NOT close through opposite side
  → OB becomes Mitigation Block — still high probability, tag separately

BREAKER: Price closes THROUGH the OB entirely without reacting
  → OB flips: Bullish OB becomes Bearish Breaker, Bearish OB becomes Bullish Breaker

--- KILL ZONE INTEGRATION ---
Show nearest OB and FVG in bias direction for each active kill zone.
If price is at an OB + FVG + inside kill zone → alert fires.

DISPLAY: All OBs on chart as filled rectangles.
  Bullish OB = green; Bearish OB = red; Breaker = purple; Mitigation = amber
  FVGs = dashed outline rectangles with "FVG" label
  iFVGs = dotted outline with "iFVG" label
  Dashboard list: Type | TF | Top | Bottom | Fresh/Mitigated | Distance

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODULE 5 — 71% FIBONACCI ENGINE (OTE Setup)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONCEPT: After an impulse move, price retraces to 61.8–78.6% before
continuing. Institutions place limit orders at 71% (OTE — Optimal Trade Entry).

LEVEL CALCULATION (bullish example — user marks swing high + low):
  range = swingHigh - swingLow
  0%   = swingHigh (top of the move)
  23.6 = swingHigh - range*0.236
  38.2 = swingHigh - range*0.382
  50.0 = swingHigh - range*0.500  (equilibrium)
  61.8 = swingHigh - range*0.618  (OTE zone top)
  70.5 = swingHigh - range*0.705
  71.0 = swingHigh - range*0.710  ← PRIMARY ENTRY
  78.6 = swingHigh - range*0.786  (OTE zone bottom / hard invalidation)
  100% = swingLow  (full retracement = setup invalid)

For bearish: mirror (add instead of subtract from swingLow)

OTE ZONE: 61.8% to 78.6% — watch for entries anywhere in here
PRIMARY ENTRY: 71% — place limit order here
INVALIDATION: close beyond 100% (price took out the swing that defined the move)

CONFLUENCE SCORING (score out of 5):
  +1 Active kill zone
  +1 OB body within 5 pips of 71% level
  +1 FVG overlapping 71% level
  +1 S&D strong zone at or near 71% level
  +1 PO3 weekly AND daily bias match the trade direction

  4/5 or 5/5 → TAKE SETUP (alert fires)
  3/5        → WATCH (no alert, display amber)
  <3/5       → SKIP (greyed out)

DISPLAY: Fib tool activated by user marking swing points on chart.
  All levels drawn as horizontal lines with labels.
  OTE zone = gold shaded band between 61.8% and 78.6%.
  71% = bright gold dashed line.
  Confluence score badge shown on the chart at the 71% level.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODULE 6 — EXECUTION LAYER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

--- PRE-FLIGHT CHECKLIST (runs before EVERY order) ---
7 checks — ALL must pass or order is BLOCKED:
  1. PO3 confluence = HIGH and matches trade direction
  2. Active kill zone (London or NY only — not Asian, not London Close)
  3. Validated entry zone (STRONG S&D zone OR fresh OB OR unfilled FVG)
  4. Price in OTE zone (61.8%–78.6%) OR at validated OB/FVG
  5. Risk % ≤ 2% of account (hard cap — cannot be overridden)
  6. No high-impact economic event within 30 minutes
  7. Reward-to-risk ≥ 3:1

Show checklist in a modal before order placement.
Green check = pass, Red X = fail with specific reason.
BLOCK ORDER button appears if any fail. CONFIRM ORDER button appears only if all pass.

--- RISK ENGINE ---
Inputs: accountBalance, riskPercent (default 1%, max 2%), entry, stopLoss, instrument
riskAmount = accountBalance * (riskPercent/100)
pipRisk = |entry - stopLoss| / pipValue[instrument]
lotSize = riskAmount / (pipRisk * pipValueDollars[instrument])
Round lotSize DOWN to nearest 0.01

Show: Dollar risk | Pip risk | Lot size | Target at 1R | Target at 2R | Target at 3R

--- ORDER TYPES ---
Market order: execute at current price via MT5 API
Limit order: place pending at specified price
Stop order: place stop entry at specified price
Bulk pending: set multiple limit orders across a zone (e.g. 3 orders spaced through demand zone)

--- TRADE MANAGEMENT ---
Break Even: auto-move SL to entry+1pip when price hits 1:1 RR
Trailing Stop:
  ATR-based: SL trails at price - (ATR_14 * multiplier)
  Fixed pip: SL trails at fixed pip distance below price
Partial Close: close 50% of position at 1:1, remainder targets 3:1
Manual override: full control at all times via trade card

--- PRICE ALERTS ---
Set alert on any price level for any instrument
Alert types: price touch | candle close above/below | zone entry (price enters S&D zone)
Notification: in-app toast + sound chime + browser push notification
Alert persists in localStorage

--- BULK OPERATIONS ---
Select multiple trades via checkboxes.
Actions: Move all to BE | Close all profitable | Close all in loss |
         Set trail on all | Reverse all positions | Close all flat

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODULE 7 — MEASURED MOVE & PD ARRAY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MEASURED MOVE:
  User marks consolidation high and low.
  zoneHeight = high - low
  Bullish target = breakout level + zoneHeight
  Bearish target = breakout level - zoneHeight
  Show in pips and percentage move.

LIQUIDITY TARGETS:
  Prev weekly high/low, prev daily high/low
  Equal highs: 2+ swing highs within 5 pips → buy-side liquidity pool
  Equal lows: 2+ swing lows within 5 pips → sell-side liquidity pool
  These are the REAL price targets for swing trades.

PD ARRAY:
  equilibrium = rangeLow + (range * 0.50)
  premium = above equilibrium (sell from here)
  discount = below equilibrium (buy from here)
  OTE levels: 61.8%, 70.5%, 78.6% from range extremes
  Overlay all OBs, FVGs, S&D zones on PD array view.
  RULE: Only buy in discount, only sell in premium.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODULE 8 — MACRO INTELLIGENCE LAYER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Central bank stance tracker: Fed, ECB, BOE, BOJ, RBA, RBNZ, SNB
  Each bank: Hawkish / Neutral / Dovish (user-updatable cards)
  Rate differential table: rank pairs by interest rate spread
  Pair with highest divergence = strongest trending bias

DXY strength meter: correlated to XAUUSD, AUDUSD, USDJPY
  DXY rising → bearish Gold, bearish AUD pairs, bullish JPY pairs

Economic calendar: pull from free API (Investing.com or similar)
  High-impact events marked on the kill zone timeline
  Pre-event warning fires 30 minutes before any high-impact event
  Post-event: prompt user to reassess open trade bias

Instrument selection filter: ranks instruments by macro + PO3 alignment
  Best trade opportunities surfaced to top of watchlist

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODULE 9 — DASHBOARD & CHART UI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LAYOUT:
  Left sidebar (64px): icon nav for each module
  Top bar: instrument price ticker strip (live), active kill zone badge,
           weekly and daily bias per selected instrument
  Main area: tabbed content based on active module
  Right panel (320px): open trades + alerts + pre-flight

INSTRUMENT SIDEBAR:
  Supported: EURUSD, GBPUSD, GBPJPY, USDJPY, AUDUSD, NZDUSD,
             USDCAD, XAUUSD, US30, NAS100, USOIL
  Each instrument shows: live price, direction arrow, bias badge

CHART (lightweight-charts v4):
  Candlestick chart per instrument, switchable TF (W1/D1/H8)
  Auto-drawn overlays:
    S&D zones (filled rectangles, proximal/distal lines)
    OBs (filled rectangles, color-coded by type)
    FVGs (dashed outlines)
    iFVGs (dotted outlines)
    Fib levels (horizontal lines, OTE zone shaded gold)
    Kill zone time bands (vertical shaded regions)
    Prev weekly high/low (dashed horizontal lines)
    Prev daily high/low (dotted horizontal lines)
    PD array equilibrium line

WAR ROOM (watchlist):
  Grid of instrument cards. Each card:
    Instrument name | Live price | Change %
    Weekly bias badge | Daily bias badge
    Confluence status
    Nearest STRONG zone (type + distance in pips)
    Active kill zone countdown
    Confluence score (if 71% setup forming)
  Green border = bullish high confluence
  Red border = bearish high confluence
  Grey border = neutral or conflicting

OPEN TRADES PANEL:
  List of all open trades:
    Instrument | Direction | Entry | Current | Pips | P&L ($) | RR current
    Status bar: SL level | TP level | BE moved? | Trail active?
    Action buttons: Close | BE | Trail | Partial | Edit
  Summary row: Total open P&L, total risk deployed

WEEKLY BRIEFING (auto-generated Sunday):
  For each instrument: W bias + D bias + strongest zone in play
  This week's high-impact events
  Which kill zones are most active this week (DST consideration)
  Top 3 setups approaching entry zone with confluence scores

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INSTRUMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EURUSD  GBPUSD  GBPJPY  USDJPY  AUDUSD  NZDUSD  USDCAD
XAUUSD (Gold)  US30 (Dow Jones)  NAS100 (Nasdaq)  USOIL (Crude)

pipValue: EURUSD/GBPUSD/AUDUSD/NZDUSD/USDCAD = 0.0001
          GBPJPY/USDJPY = 0.01
          XAUUSD = 0.01
          US30/NAS100 = 1.0
          USOIL = 0.01

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PERSISTENCE (localStorage keys)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sdt_account       → { balance, riskPercent, broker_url }
sdt_watchlist     → [instrument, ...]
sdt_open_trades   → [{ id, instrument, direction, entry, sl, tp, size, ... }]
sdt_sd_zones      → { EURUSD: [...zones], GBPUSD: [...zones], ... }
sdt_alerts        → [{ instrument, level, type, triggered }]
sdt_macro         → { cb_stances: {...}, last_updated }
sdt_weekly_bias   → { EURUSD: { bias, rule, prev_high, prev_low }, ... }
sdt_fib_levels    → { EURUSD: { swingHigh, swingLow, levels }, ... }
sdt_preferences   → { theme, defaultTF, notifications }

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTERCONNECTION RULES (everything talks to everything)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PO3 Bias → feeds Kill Zone panel (buy or sell label)
PO3 Bias → feeds Pre-Flight Checker (check 1)
Kill Zone status → feeds Pre-Flight Checker (check 2)
S&D Zones → fed into Pre-Flight Checker (check 3)
S&D Zones → drawn on chart automatically
FVGs/OBs → drawn on chart automatically
FVGs/OBs → fed into Kill Zone panel (nearest structure per zone)
71% Fib → confluence scored using all other modules
71% Fib → drawn on chart when swing points marked
Macro bias → feeds instrument ranking in war room
Economic calendar → feeds Pre-Flight Checker (check 6)
Risk Engine → calculates from entry/SL marked on chart
Pre-Flight → gates ALL order placement
Price alerts → monitor live feed and fire on condition match

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUILD THIS IN STAGES — DO NOT BUILD ALL AT ONCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage 1: UI shell + nav + dark theme + instrument sidebar
Stage 2: MT5 price feed integration + live price display
Stage 3: PO3 Bias Engine (weekly + daily bias cards)
Stage 4: Kill Zone countdowns + bias integration
Stage 5: S&D Zone detection engine + zone dashboard table
Stage 6: FVG + OB + iFVG + Breaker detection
Stage 7: 71% Fib tool + confluence scorer
Stage 8: Pre-Flight checklist + Risk engine
Stage 9: Order placement (market, limit, stop, bulk)
Stage 10: Trade management (BE, trail, partial close)
Stage 11: Measured move + PD Array + liquidity targets
Stage 12: Macro intelligence layer
Stage 13: Chart overlays (zones, OBs, FVGs, fibs, kill zones)
Stage 14: Weekly briefing generator
Stage 15: Bulk operations + price alerts
Stage 16: Polish, animations, mobile responsiveness

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
START WITH STAGE 1 NOW.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Build the full UI shell: dark terminal layout, left icon sidebar,
top price ticker bar, main content area, right trades panel.
Make it stunning. Use the exact colors specified above.
Include placeholder sections for all modules.
No functionality yet — just the frame. Make it look like a
professional trading terminal that a prop trader would pay for.
```

---

## QUICK REFERENCE: MATHEMATICS SUMMARY

| Concept | Key Formula |
|---|---|
| Bullish Weekly Bias | `curr_close > prev_high` |
| Bearish Weekly Bias (sweep) | `curr_high > prev_high AND curr_close < prev_high AND curr_close < prev_open` |
| Base Candle | `body/range < 0.4 AND range < avgRange*0.6` |
| Impulsive Move | `totalMove_3candles > avgRange*1.5` |
| Demand Zone Proximal | `max(close) of base candles` |
| Supply Zone Proximal | `min(close) of base candles` |
| Zone STRONG | `impulse closed through nearest opposing zone` |
| Bullish FVG | `c3.low > c1.high AND c2 bullish` |
| Bearish FVG | `c1.low > c3.high AND c2 bearish` |
| Bullish OB | `last bearish candle before bullish impulse > 1.5x avgRange` |
| 71% Fib Entry | `swingHigh - (swingHigh - swingLow) * 0.71` |
| OTE Zone | `61.8% to 78.6% retracement` |
| PD Equilibrium | `rangeLow + (range * 0.50)` |
| Position Size | `(accountBalance * riskPct) / (pipRisk * pipValueDollars)` |
| Measured Move Target | `breakoutLevel + zoneHeight` |
| Min RR Required | `3:1` |
| Max Risk Per Trade | `2% of account (hard cap)` |

---

*The Swing Desk Terminal — Build Plan v1.0*
*Total: 9 Modules | 34+ Sub-Components | 16 Build Stages*
*All concepts, mathematics, and detection logic defined for AI-assisted development*
