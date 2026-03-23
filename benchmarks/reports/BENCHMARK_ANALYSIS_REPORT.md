# MiniMCP vs FastMCP vs MCP Low-Level: Comprehensive Benchmark Analysis

> **Note**: Benchmarked against the standalone [`fastmcp`](https://github.com/jlowin/fastmcp)
> package (v3.1.1, by Jeremiah Lowin) and the official MCP Python SDK
> [`mcp`](https://github.com/modelcontextprotocol/python-sdk) low-level server (v1.24.0).

Benchmarked across all 3 transport types, 3 workload patterns, and 4 load levels,
MiniMCP is the fastest server in every one of the 36 test scenarios, outperforming
both FastMCP and MCP Low-Level at every concurrency level.

---

## 🏆 Overall Winner

### 🥇 MiniMCP

MiniMCP is #1 across all 36 scenarios. The competitive picture differs by transport:

- **STDIO**: MCP Low-Level (the raw SDK implementation) beats FastMCP, placing
  second — but MiniMCP is still ~2× faster than FastMCP and ~50% faster than
  MCP Low-Level at high concurrency.
- **HTTP / Streamable HTTP**: MCP Low-Level struggles with concurrent connections
  and becomes *slower* than FastMCP at medium and heavy load, placing third. MiniMCP
  leads both by a wide margin.
- **Memory (STDIO)**: MiniMCP and MCP Low-Level are comparably lean (~20 MB and
  ~23 MB at heavy load); FastMCP consumes ~47 MB.
- **Memory (HTTP)**: MiniMCP's ~22 MB footprint is dramatically smaller than both
  FastMCP (~63 MB) and MCP Low-Level (~56 MB) at heavy load, both of which grow
  with concurrency while MiniMCP stays nearly flat.

---

## 🖥️ Test Environment

| Property                 | Value                        |
|--------------------------|------------------------------|
| **Date**                 | 2026-03-22                   |
| **OS**                   | Linux 6.8.0-106-generic      |
| **Architecture**         | x86\_64                      |
| **CPU (logical)**        | 32 cores                     |
| **CPU (physical)**       | 24 cores                     |
| **RAM**                  | 62.6 GB                      |
| **Python**               | 3.10.12                      |
| **MiniMCP**              | 0.5.0                        |
| **FastMCP** (standalone) | 3.1.1                        |
| **MCP Low-Level** (SDK)  | 1.24.0                       |
| **anyio**                | 4.12.0                       |
| **uvicorn**              | 0.38.0                       |
| **starlette**            | 0.50.0                       |
| **Total Duration**       | ~9.3 hours                   |

### ⚙️ Load Profiles

| Load       | Concurrency | Iterations | Rounds | Total Requests/Server |
|------------|-------------|------------|--------|-----------------------|
| Sequential | 1           | 30         | 40     | 1,200                 |
| Light      | 20          | 30         | 40     | 24,000                |
| Medium     | 100         | 15         | 40     | 60,000                |
| Heavy      | 300         | 15         | 40     | 180,000               |

---

## 🎯 Key Findings

1. 🚀 **STDIO is MiniMCP's dominant transport**: MiniMCP handles STDIO requests
   ~2× faster than FastMCP and ~50% faster than MCP Low-Level at heavy concurrency.
   The ranking is MiniMCP → MCP Low-Level → FastMCP, and the gap holds rock-steady
   from sequential through heavy load.

2. 🌐 **HTTP reveals MCP Low-Level's concurrency limits**: On HTTP and Streamable
   HTTP, the raw SDK reference implementation is the *slowest* at medium and heavy
   load — ~2× slower than MiniMCP and trailing MiniMCP by ~78% on throughput. Its
   per-connection setup costs do not amortize under concurrency; it plateaus at
   ~180 RPS regardless of load level.

3. 💾 **Memory tells two different stories by transport**: For STDIO, MiniMCP
   and MCP Low-Level are comparably lean at low load (within ~4%), but MiniMCP
   is 14% more efficient at heavy load — both far below FastMCP. For HTTP,
   MiniMCP's flat ~22 MB profile is dramatically better than both FastMCP (~63 MB)
   and MCP Low-Level (~56 MB), which both grow substantially with concurrency.

4. ✅ **MiniMCP wins all 36 test scenarios against both competitors**: 9 benchmark
   files × 4 load levels, on both response time and throughput. There are no
   exceptions.

---

## 📊 Findings by Transport

### 📡 STDIO Transport

The ranking is MiniMCP > MCP Low-Level > FastMCP. MCP Low-Level, being close to
the protocol layer, handles STDIO more efficiently than FastMCP's heavier framework
— but MiniMCP beats both. MCP Low-Level is within 21% of MiniMCP at sequential
load; that gap grows to ~51% at heavy concurrency.

#### STDIO — Sync tool (`compute_all_prime_factors`) — Response Time

| Load       |  c  | MiniMCP | FastMCP | LowLevel | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|----------|-------------|-------------|
| Sequential |   1 |   1.1ms |   2.4ms |    1.4ms | **+54%**    | **+21%**    |
| Light      |  20 |   9.1ms |  25.4ms |   17.6ms | **+64%**    | **+48%**    |
| Medium     | 100 |  43.3ms | 120.6ms |   86.7ms | **+64%**    | **+50%**    |
| Heavy      | 300 | 128.6ms | 358.6ms |  262.6ms | **+64%**    | **+51%**    |

#### STDIO — Sync tool — Throughput RPS

| Load       |  c  | MiniMCP | FastMCP | LowLevel | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|----------|-------------|-------------|
| Sequential |   1 |     852 |     397 |      701 | **+115%**   | **+22%**    |
| Light      |  20 |   1,226 |     543 |      839 | **+126%**   | **+46%**    |
| Medium     | 100 |   1,194 |     549 |      830 | **+118%**   | **+44%**    |
| Heavy      | 300 |   1,185 |     549 |      822 | **+116%**   | **+44%**    |

#### STDIO — Noop tool (protocol overhead only) — Response Time

| Load       |  c  | MiniMCP | FastMCP | LowLevel | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|----------|-------------|-------------|
| Sequential |   1 |   1.1ms |   2.4ms |    1.4ms | **+54%**    | **+21%**    |
| Light      |  20 |   9.2ms |  23.9ms |   17.6ms | **+62%**    | **+48%**    |
| Medium     | 100 |  43.7ms | 112.7ms |   86.5ms | **+61%**    | **+49%**    |
| Heavy      | 300 | 129.2ms | 334.9ms |  259.7ms | **+61%**    | **+50%**    |

#### STDIO — Noop tool — Throughput RPS

| Load       |  c  | MiniMCP | FastMCP | LowLevel | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|----------|-------------|-------------|
| Sequential |   1 |     839 |     409 |      696 | **+105%**   | **+21%**    |
| Light      |  20 |   1,219 |     566 |      838 | **+115%**   | **+45%**    |
| Medium     | 100 |   1,186 |     579 |      831 | **+105%**   | **+43%**    |
| Heavy      | 300 |   1,181 |     576 |      827 | **+105%**   | **+43%**    |

#### STDIO — I/O-bound async tool (`io_bound_compute_all_prime_factors`) — Response Time

| Load       |  c  | MiniMCP | FastMCP | LowLevel | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|----------|-------------|-------------|
| Sequential |   1 |   3.3ms |   4.6ms |    3.6ms | **+28%**    | **+8%**     |
| Light      |  20 |  10.9ms |  25.6ms |   19.5ms | **+57%**    | **+44%**    |
| Medium     | 100 |  43.9ms | 118.9ms |   90.6ms | **+63%**    | **+52%**    |
| Heavy      | 300 | 130.2ms | 350.6ms |  270.7ms | **+63%**    | **+52%**    |

#### STDIO — I/O-bound async tool — Throughput RPS

| Load       |  c  | MiniMCP | FastMCP | LowLevel | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|----------|-------------|-------------|
| Sequential |   1 |     294 |     215 |      271 | **+37%**    | **+8%**     |
| Light      |  20 |   1,120 |     572 |      803 | **+96%**    | **+39%**    |
| Medium     | 100 |   1,232 |     564 |      798 | **+118%**   | **+54%**    |
| Heavy      | 300 |   1,196 |     563 |      792 | **+112%**   | **+51%**    |

> 🔥 **STDIO Headline**: MiniMCP exceeds 1,100 RPS on all STDIO workloads once
> concurrency kicks in (c ≥ 20), peaking at 1,232 RPS. FastMCP peaks at ~580 RPS,
> MCP Low-Level at ~840 RPS. MiniMCP's ~64% response-time advantage over FastMCP
> and ~51% over MCP Low-Level at heavy load are completely stable — no degradation
> as concurrency rises.

---

### 🌐 HTTP Transport

The ranking flips for MCP Low-Level on HTTP. Its per-connection setup costs are
acceptable at sequential load (7.2ms vs MiniMCP's 3.0ms), but do not amortize
under concurrency — it plateaus at ~180 RPS and remains there regardless of
concurrency level, making it the slowest server at medium and heavy load.

#### HTTP — Sync tool — Response Time

| Load       |  c  | MiniMCP | FastMCP | LowLevel   | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|------------|-------------|-------------|
| Sequential |   1 |   3.0ms |   6.3ms |      7.2ms | **+52%**    | **+58%**    |
| Light      |  20 |  44.3ms |  71.7ms |    111.0ms | **+38%**    | **+60%**    |
| Medium     | 100 | 225.2ms | 275.6ms |    489.8ms | **+18%**    | **+54%**    |
| Heavy      | 300 | 632.0ms | 778.7ms |  1,427.1ms | **+19%**    | **+56%**    |

#### HTTP — Sync tool — Throughput RPS

| Load       |  c  | MiniMCP | FastMCP | LowLevel | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|----------|-------------|-------------|
| Sequential |   1 |     324 |     156 |      137 | **+108%**   | **+136%**   |
| Light      |  20 |     313 |     215 |      168 | **+46%**    | **+86%**    |
| Medium     | 100 |     294 |     240 |      181 | **+23%**    | **+62%**    |
| Heavy      | 300 |     321 |     239 |      180 | **+34%**    | **+78%**    |

#### HTTP — Noop tool — Response Time

| Load       |  c  | MiniMCP | FastMCP | LowLevel   | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|------------|-------------|-------------|
| Sequential |   1 |   3.0ms |   6.2ms |      7.2ms | **+52%**    | **+58%**    |
| Light      |  20 |  44.3ms |  64.3ms |    110.9ms | **+31%**    | **+60%**    |
| Medium     | 100 | 225.4ms | 257.7ms |    488.0ms | **+13%**    | **+54%**    |
| Heavy      | 300 | 632.2ms | 735.2ms |  1,427.5ms | **+14%**    | **+56%**    |

#### HTTP — Noop tool — Throughput RPS

| Load       |  c  | MiniMCP | FastMCP | LowLevel | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|----------|-------------|-------------|
| Sequential |   1 |     323 |     157 |      137 | **+106%**   | **+136%**   |
| Light      |  20 |     312 |     231 |      168 | **+35%**    | **+86%**    |
| Medium     | 100 |     294 |     253 |      181 | **+16%**    | **+62%**    |
| Heavy      | 300 |     321 |     252 |      180 | **+27%**    | **+78%**    |

#### HTTP — I/O-bound async tool — Response Time

| Load       |  c  | MiniMCP | FastMCP | LowLevel   | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|------------|-------------|-------------|
| Sequential |   1 |   5.0ms |   8.1ms |      9.6ms | **+38%**    | **+48%**    |
| Light      |  20 |  50.1ms |  67.1ms |    113.2ms | **+25%**    | **+56%**    |
| Medium     | 100 | 254.9ms | 266.3ms |    515.5ms | **+4%**     | **+51%**    |
| Heavy      | 300 | 683.3ms | 754.2ms |  1,527.2ms | **+9%**     | **+55%**    |

#### HTTP — I/O-bound async tool — Throughput RPS

| Load       |  c  | MiniMCP | FastMCP | LowLevel | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|----------|-------------|-------------|
| Sequential |   1 |     195 |     122 |      103 | **+60%**    | **+89%**    |
| Light      |  20 |     283 |     227 |      168 | **+25%**    | **+68%**    |
| Medium     | 100 |     264 |     248 |      181 | **+6%**     | **+46%**    |
| Heavy      | 300 |     298 |     246 |      180 | **+21%**    | **+66%**    |

> 💡 **HTTP Headline**: MiniMCP's 3ms per-request cost (vs 6ms FastMCP, 7ms Low-Level)
> translates to 2× higher throughput at sequential load. At medium/heavy load the
> MiniMCP–FastMCP gap narrows to 13–19% for noop/sync tools and 4–11% for I/O-bound
> tools due to FastMCP's heavier protocol overhead enabling better HTTP socket
> pipelining. MCP Low-Level never benefits from this and tops out at ~180 RPS
> regardless of load — a 78% throughput deficit vs MiniMCP at heavy load. See
> [concurrency_scaling_analysis.md](../insights/concurrency_scaling_analysis.md)
> for a full architectural explanation.

---

### 🌊 Streamable HTTP Transport

Results mirror plain HTTP almost exactly, confirming that the performance profile
is driven by the MCP protocol layer rather than the specific HTTP framing.

#### Streamable HTTP — Sync tool — Response Time

| Load       |  c  | MiniMCP | FastMCP | LowLevel   | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|------------|-------------|-------------|
| Sequential |   1 |   3.1ms |   6.3ms |      7.2ms | **+51%**    | **+57%**    |
| Light      |  20 |  44.2ms |  71.6ms |    110.8ms | **+38%**    | **+60%**    |
| Medium     | 100 | 223.1ms | 275.8ms |    489.7ms | **+19%**    | **+54%**    |
| Heavy      | 300 | 628.4ms | 779.7ms |  1,429.7ms | **+19%**    | **+56%**    |

#### Streamable HTTP — Sync tool — Throughput RPS

| Load       |  c  | MiniMCP | FastMCP | LowLevel | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|----------|-------------|-------------|
| Sequential |   1 |     315 |     156 |      137 | **+102%**   | **+130%**   |
| Light      |  20 |     311 |     215 |      169 | **+45%**    | **+84%**    |
| Medium     | 100 |     298 |     240 |      182 | **+24%**    | **+64%**    |
| Heavy      | 300 |     323 |     240 |      180 | **+35%**    | **+79%**    |

#### Streamable HTTP — Noop tool — Response Time

| Load       |  c  | MiniMCP | FastMCP | LowLevel   | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|------------|-------------|-------------|
| Sequential |   1 |   3.1ms |   6.2ms |      7.1ms | **+50%**    | **+56%**    |
| Light      |  20 |  44.2ms |  64.4ms |    110.7ms | **+31%**    | **+60%**    |
| Medium     | 100 | 223.2ms | 257.8ms |    488.1ms | **+13%**    | **+54%**    |
| Heavy      | 300 | 627.6ms | 736.6ms |  1,428.5ms | **+15%**    | **+56%**    |

#### Streamable HTTP — Noop tool — Throughput RPS

| Load       |  c  | MiniMCP | FastMCP | LowLevel | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|----------|-------------|-------------|
| Sequential |   1 |     317 |     157 |      138 | **+102%**   | **+130%**   |
| Light      |  20 |     311 |     231 |      169 | **+35%**    | **+84%**    |
| Medium     | 100 |     298 |     254 |      182 | **+17%**    | **+64%**    |
| Heavy      | 300 |     323 |     252 |      180 | **+28%**    | **+79%**    |

#### Streamable HTTP — I/O-bound async tool — Response Time

| Load       |  c  | MiniMCP | FastMCP | LowLevel   | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|------------|-------------|-------------|
| Sequential |   1 |   5.0ms |   8.1ms |      9.6ms | **+38%**    | **+48%**    |
| Light      |  20 |  47.2ms |  67.2ms |    113.0ms | **+30%**    | **+58%**    |
| Medium     | 100 | 236.4ms | 266.1ms |    515.3ms | **+11%**    | **+54%**    |
| Heavy      | 300 | 673.8ms | 754.7ms |  1,526.7ms | **+11%**    | **+56%**    |

#### Streamable HTTP — I/O-bound async tool — Throughput RPS

| Load       |  c  | MiniMCP | FastMCP | LowLevel | vs FastMCP  | vs LowLevel |
|------------|-----|---------|---------|----------|-------------|-------------|
| Sequential |   1 |     197 |     121 |      102 | **+63%**    | **+93%**    |
| Light      |  20 |     303 |     227 |      168 | **+33%**    | **+80%**    |
| Medium     | 100 |     283 |     248 |      182 | **+14%**    | **+55%**    |
| Heavy      | 300 |     302 |     246 |      180 | **+23%**    | **+68%**    |

> 📝 **Streamable HTTP Headline**: Results are nearly identical to plain HTTP,
> confirming that the performance characteristics are driven by the MCP protocol
> layer rather than the specific HTTP framing.

---

## 💾 Memory Usage

MiniMCP's memory footprint is dramatically smaller and more stable under load.
The pattern differs by transport:

- **STDIO**: MiniMCP and MCP Low-Level are comparably lean at low concurrency
  (within ~4%), both far below FastMCP. At heavy load MiniMCP is 14% lower than
  MCP Low-Level and 57% lower than FastMCP.
- **HTTP / Streamable HTTP**: MiniMCP stands alone. Both FastMCP and MCP Low-Level
  grow substantially with concurrency (reaching ~56–63 MB at heavy load), while
  MiniMCP stays nearly flat at ~22 MB.

### Peak memory usage at heavy load (c=300)

| Transport          | Workload  | MiniMCP | FastMCP | LowLevel | vs FastMCP | vs LowLevel |
|--------------------|-----------|---------|---------|----------|------------|-------------|
| 📡 STDIO           | Sync      | 20.1 MB | 46.6 MB |  23.4 MB | **−57%**   | **−14%**    |
| 📡 STDIO           | Noop      | 20.1 MB | 46.5 MB |  23.3 MB | **−57%**   | **−14%**    |
| 📡 STDIO           | I/O-bound | 20.2 MB | 46.7 MB |  23.4 MB | **−57%**   | **−14%**    |
| 🌐 HTTP            | Sync      | 21.5 MB | 62.8 MB |  56.3 MB | **−66%**   | **−62%**    |
| 🌐 HTTP            | Noop      | 21.5 MB | 62.1 MB |  56.4 MB | **−65%**   | **−62%**    |
| 🌐 HTTP            | I/O-bound | 22.0 MB | 62.4 MB |  56.2 MB | **−65%**   | **−61%**    |
| 🌊 Streamable HTTP | Sync      | 22.0 MB | 62.9 MB |  56.3 MB | **−65%**   | **−61%**    |
| 🌊 Streamable HTTP | Noop      | 22.1 MB | 62.1 MB |  56.1 MB | **−64%**   | **−61%**    |
| 🌊 Streamable HTTP | I/O-bound | 22.0 MB | 62.3 MB |  56.2 MB | **−65%**   | **−61%**    |

For STDIO, MCP Low-Level is lean like MiniMCP at low-to-medium concurrency but
diverges at heavy load (23.4 MB vs 20.1 MB). FastMCP's two-task-per-request
model consumes ~2× more memory than MiniMCP across all STDIO load levels.

For HTTP transports, MCP Low-Level's memory growth pattern mirrors FastMCP's —
both scale poorly with concurrency. MiniMCP's stateless single-task model keeps
its memory essentially flat regardless of load level.

---

## 📈 Summary Statistics

### ⏱️ Response Time: MiniMCP advantage over FastMCP

| Load Level  | 📡 STDIO         | 🌐 HTTP (Sync/Noop) | 🌐 HTTP (I/O-bound) |
|-------------|------------------|---------------------|---------------------|
| Sequential  | +28% to +54%     | +52%                | +38%                |
| Light       | +57% to +64%     | +31% to +38%        | +25% to +30%        |
| Medium      | +61% to +64%     | +13% to +19%        | +4% to +11%         |
| Heavy       | +61% to +64%     | +14% to +19%        | +9% to +11%         |

### ⏱️ Response Time: MiniMCP advantage over MCP Low-Level

| Load Level  | 📡 STDIO         | 🌐 HTTP (Sync/Noop) | 🌐 HTTP (I/O-bound) |
|-------------|------------------|---------------------|---------------------|
| Sequential  | +8% to +21%      | +57% to +58%        | +48%                |
| Light       | +44% to +48%     | +60%                | +56% to +58%        |
| Medium      | +49% to +52%     | +54%                | +51% to +54%        |
| Heavy       | +50% to +52%     | +56%                | +55% to +56%        |

### 🚀 Throughput: MiniMCP advantage over FastMCP

| Load Level  | 📡 STDIO           | 🌐 HTTP (Sync/Noop) | 🌐 HTTP (I/O-bound) |
|-------------|--------------------|--------------------|---------------------|
| Sequential  | +37% to +115%      | +102% to +108%     | +60% to +63%        |
| Light       | +96% to +126%      | +35% to +46%       | +25% to +33%        |
| Medium      | +105% to +118%     | +16% to +24%       | +6% to +14%         |
| Heavy       | +105% to +116%     | +27% to +35%       | +21% to +23%        |

### 🚀 Throughput: MiniMCP advantage over MCP Low-Level

| Load Level  | 📡 STDIO           | 🌐 HTTP (Sync/Noop) | 🌐 HTTP (I/O-bound) |
|-------------|--------------------|--------------------|---------------------|
| Sequential  | +8% to +22%        | +130% to +136%     | +89% to +93%        |
| Light       | +39% to +46%       | +84% to +86%       | +68% to +80%        |
| Medium      | +43% to +54%       | +62% to +64%       | +46% to +55%        |
| Heavy       | +43% to +51%       | +78% to +79%       | +66% to +68%        |

### 💾 Memory: MiniMCP advantage over FastMCP

| Load Level  | 📡 STDIO   | 🌐 HTTP transports |
|-------------|------------|--------------------|
| Sequential  | −47%       | −44% to −45%       |
| Light       | −48%       | −46% to −48%       |
| Medium      | −51%       | −53% to −54%       |
| Heavy       | **−57%**   | **−64% to −66%**   |

### 💾 Memory: MiniMCP advantage over MCP Low-Level

| Load Level  | 📡 STDIO             | 🌐 HTTP transports |
|-------------|----------------------|--------------------|
| Sequential  | comparable (within 4%) | comparable (within 4%) |
| Light       | comparable (within 4%) | −6% to −9%         |
| Medium      | comparable (within 3%) | −34% to −35%       |
| Heavy       | **−14%**             | **−61% to −62%**   |

---

## 🏁 Conclusion

**🥇 MiniMCP is the clear winner** across all 36 test scenarios against both
FastMCP and MCP Low-Level. The performance profile differs by transport:

- 📡 **STDIO**: The ranking is MiniMCP → MCP Low-Level → FastMCP. MCP Low-Level
  is a credible second — closer to the protocol, it avoids FastMCP's framework
  overhead. But MiniMCP leads by ~50% at high concurrency, and the advantage
  grows as load increases. For any stdio-based MCP deployment, the choice is
  unambiguous.

- 🌐 **HTTP / Streamable HTTP at low concurrency**: MiniMCP's 3ms per-request
  cost is ~2× lower than FastMCP and ~2.4× lower than MCP Low-Level, translating
  directly into >2× throughput advantage at sequential load.

- ⚡ **HTTP / Streamable HTTP at high concurrency**: MCP Low-Level stalls at
  ~180 RPS regardless of load (78% throughput deficit vs MiniMCP at heavy). FastMCP
  partially closes the gap via better HTTP socket pipelining at high concurrency
  (settling at 6–35% behind MiniMCP on throughput across all workloads), but never overtakes it.
  MiniMCP is the only server that handles high concurrency efficiently across all
  transports.

- 💾 **Memory**: On STDIO, MiniMCP and MCP Low-Level are both efficient — they
  stay within ~4% of each other at low load, with MiniMCP pulling ahead by 14%
  at heavy load. Both are far below FastMCP's 47 MB. On HTTP transports, MiniMCP's
  ~22 MB flat profile at heavy load stands far apart from both FastMCP (~63 MB)
  and MCP Low-Level (~56 MB), which grow with concurrency.

**✅ Recommendation**: Use MiniMCP for all production deployments. It outperforms
the leading high-level framework (FastMCP) and the raw protocol SDK (MCP Low-Level)
across every transport and workload. The advantage is largest at low-to-medium
concurrency — the common production case — remains meaningful at high concurrency,
and comes with a dramatically lower memory footprint on HTTP transports.

---

*Generated from benchmark results dated 2026-03-22.*
*Benchmarks run on Linux 6.8.0-106-generic, Python 3.10.12, 24-core x86\_64, 62.6 GB RAM.*
