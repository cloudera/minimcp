# MiniMCP vs FastMCP (standalone): Comprehensive Benchmark Analysis

> **Note**: Benchmarked against the standalone [`fastmcp`](https://github.com/jlowin/fastmcp)
> package (v3.1.1, by Jeremiah Lowin).

Benchmarked across all 3 transport types, 3 workload patterns, and 4 load levels,
MiniMCP is consistently faster than FastMCP in every one of the 36 test scenarios.

---

## 🏆 Overall Winner

### 🥇 MiniMCP

MiniMCP outperforms FastMCP across every transport, every workload, and every
concurrency level. The advantage is most dramatic on STDIO (2× faster, 2× the
throughput) and most modest on HTTP transports under very high concurrency with
async I/O-bound tools, where the gap narrows to ~10% — but never disappears.
MiniMCP also uses dramatically less memory (44–66% less) at every load level.

---

## 🖥️ Test Environment

| Property           | Value                        |
|--------------------|------------------------------|
| **Date**           | 2026-03-21                   |
| **OS**             | Linux 6.8.0-106-generic      |
| **Architecture**   | x86\_64                      |
| **CPU (logical)**  | 32 cores                     |
| **CPU (physical)** | 24 cores                     |
| **RAM**            | 62.6 GB                      |
| **Python**         | 3.10.12                      |
| **MiniMCP**        | 0.4.1                        |
| **FastMCP** (standalone) | 3.1.1                   |
| **MCP SDK**        | 1.24.0                       |
| **anyio**          | 4.12.0                       |
| **uvicorn**        | 0.38.0                       |
| **starlette**      | 0.50.0                       |
| **Total Duration** | ~5.8 hours                   |

### ⚙️ Load Profiles

| Load       | Concurrency | Iterations | Rounds | Total Requests/Server |
|------------|-------------|------------|--------|-----------------------|
| Sequential | 1           | 30         | 40     | 1,200                 |
| Light      | 20          | 30         | 40     | 24,000                |
| Medium     | 100         | 15         | 40     | 60,000                |
| Heavy      | 300         | 15         | 40     | 180,000               |

---

## 🎯 Key Findings

1. 🚀 **STDIO is MiniMCP's strongest transport**: MiniMCP handles STDIO requests
   2× faster than FastMCP at every concurrency level, with >100% higher
   throughput. The advantage holds rock-steady from sequential through heavy load
   — FastMCP does not close the gap at all.

2. 💾 **Memory efficiency is overwhelming across the board**: MiniMCP consistently
   uses 44–57% less memory than FastMCP at low-to-medium load, and 56–66% less
   at heavy load where FastMCP's memory grows significantly with concurrency while
   MiniMCP's stays nearly flat.

3. 🌐 **HTTP advantages are real but moderate at high concurrency**: On HTTP and
   Streamable HTTP transports, MiniMCP leads by 38–53% at sequential load,
   narrowing to 13–20% for noop/sync tools at medium/heavy, and to 10–11% for
   I/O-bound tools at heavy load. MiniMCP wins every data point.

4. ✅ **MiniMCP wins all 36 test scenarios**: 9 benchmark files × 4 load levels,
   both response time and throughput. There are no exceptions.

---

## 📊 Findings by Transport

### 📡 STDIO Transport

STDIO is MiniMCP's strongest showing. The advantage is consistent and
roughly 2× across all load levels and tool types.

#### STDIO — Sync tool (`compute_all_prime_factors`)

| Load       |  c  | MiniMCP RT | FastMCP RT | RT Advantage | MiniMCP RPS | FastMCP RPS | RPS Advantage |
|------------|-----|------------|------------|--------------|-------------|-------------|---------------|
| Sequential |   1 |      1.1ms |      2.4ms |      **+53%** |         821 |         397 |      **+107%** |
| Light      |  20 |      9.1ms |     25.5ms |      **+64%** |       1,223 |         541 |      **+126%** |
| Medium     | 100 |     43.4ms |    120.8ms |      **+64%** |       1,192 |         548 |      **+118%** |
| Heavy      | 300 |    128.9ms |    356.7ms |      **+64%** |       1,184 |         550 |      **+115%** |

#### STDIO — Noop tool (protocol overhead only)

| Load       |  c  | MiniMCP RT | FastMCP RT | RT Advantage | MiniMCP RPS | FastMCP RPS | RPS Advantage |
|------------|-----|------------|------------|--------------|-------------|-------------|---------------|
| Sequential |   1 |      1.1ms |      2.4ms |      **+53%** |         849 |         410 |      **+107%** |
| Light      |  20 |      9.1ms |     24.0ms |      **+62%** |       1,226 |         566 |      **+117%** |
| Medium     | 100 |     43.4ms |    112.6ms |      **+61%** |       1,194 |         578 |      **+107%** |
| Heavy      | 300 |    128.9ms |    337.5ms |      **+62%** |       1,184 |         576 |      **+106%** |

#### STDIO — I/O-bound async tool (`io_bound_compute_all_prime_factors`)

| Load       |  c  | MiniMCP RT | FastMCP RT | RT Advantage | MiniMCP RPS | FastMCP RPS | RPS Advantage |
|------------|-----|------------|------------|--------------|-------------|-------------|---------------|
| Sequential |   1 |      3.3ms |      4.6ms |      **+28%** |         295 |         213 |       **+38%** |
| Light      |  20 |     10.9ms |     25.5ms |      **+57%** |       1,116 |         573 |       **+95%** |
| Medium     | 100 |     43.9ms |    119.1ms |      **+63%** |       1,234 |         563 |      **+119%** |
| Heavy      | 300 |    129.9ms |    350.7ms |      **+63%** |       1,199 |         562 |      **+113%** |

> 🔥 **STDIO Headline**: MiniMCP processes STDIO requests at >1,100 RPS under all
> concurrent load levels. FastMCP peaks at ~580 RPS. The ~64% response time
> advantage and ~115% RPS advantage at heavy load hold completely steady —
> no degradation at all as concurrency rises.

---

### 🌐 HTTP Transport

#### HTTP — Sync tool

| Load       |  c  | MiniMCP RT | FastMCP RT | RT Advantage | MiniMCP RPS | FastMCP RPS | RPS Advantage |
|------------|-----|------------|------------|--------------|-------------|-------------|---------------|
| Sequential |   1 |      3.0ms |      6.3ms |      **+53%** |         327 |         156 |      **+110%** |
| Light      |  20 |     44.2ms |     71.7ms |      **+38%** |         314 |         215 |       **+46%** |
| Medium     | 100 |    224.3ms |    275.4ms |      **+19%** |         296 |         240 |       **+23%** |
| Heavy      | 300 |    629.7ms |    779.3ms |      **+19%** |         323 |         240 |       **+35%** |

#### HTTP — Noop tool

| Load       |  c  | MiniMCP RT | FastMCP RT | RT Advantage | MiniMCP RPS | FastMCP RPS | RPS Advantage |
|------------|-----|------------|------------|--------------|-------------|-------------|---------------|
| Sequential |   1 |      3.0ms |      6.2ms |      **+52%** |         327 |         157 |      **+108%** |
| Light      |  20 |     44.2ms |     64.3ms |      **+31%** |         314 |         231 |       **+36%** |
| Medium     | 100 |    224.6ms |    257.9ms |      **+13%** |         296 |         254 |       **+17%** |
| Heavy      | 300 |    627.3ms |    735.2ms |      **+15%** |         324 |         252 |       **+28%** |

#### HTTP — I/O-bound async tool

| Load       |  c  | MiniMCP RT | FastMCP RT | RT Advantage | MiniMCP RPS | FastMCP RPS | RPS Advantage |
|------------|-----|------------|------------|--------------|-------------|-------------|---------------|
| Sequential |   1 |      5.0ms |      8.1ms |      **+39%** |         198 |         121 |       **+63%** |
| Light      |  20 |     50.0ms |     66.9ms |      **+25%** |         284 |         228 |       **+25%** |
| Medium     | 100 |    254.3ms |    266.1ms |       **+4%** |         265 |         248 |        **+7%** |
| Heavy      | 300 |    679.6ms |    752.1ms |      **+10%** |         300 |         246 |       **+22%** |

> 💡 **HTTP Headline**: MiniMCP's per-request cost is 2× lower (3ms vs 6ms), which
> translates directly at low concurrency. At medium/heavy load the advantage
> narrows for noop/sync tools (settling at ~19%) due to FastMCP's higher density
> of event-loop yield points enabling better HTTP socket pipelining. The I/O-bound
> tool narrows furthest (~4–10%) because its async sleeps create burst wakeups
> that proportionally benefit FastMCP's heavier protocol overhead more. See
> [concurrency_scaling_analysis.md](../insights/concurrency_scaling_analysis.md)
> for a full architectural explanation.

---

### 🌊 Streamable HTTP Transport

#### Streamable HTTP — Sync tool

| Load       |  c  | MiniMCP RT | FastMCP RT | RT Advantage | MiniMCP RPS | FastMCP RPS | RPS Advantage |
|------------|-----|------------|------------|--------------|-------------|-------------|---------------|
| Sequential |   1 |      3.1ms |      6.2ms |      **+51%** |         317 |         157 |      **+102%** |
| Light      |  20 |     44.1ms |     71.6ms |      **+38%** |         312 |         215 |       **+45%** |
| Medium     | 100 |    222.6ms |    276.7ms |      **+20%** |         299 |         239 |       **+25%** |
| Heavy      | 300 |    628.4ms |    780.2ms |      **+20%** |         323 |         240 |       **+35%** |

#### Streamable HTTP — Noop tool

| Load       |  c  | MiniMCP RT | FastMCP RT | RT Advantage | MiniMCP RPS | FastMCP RPS | RPS Advantage |
|------------|-----|------------|------------|--------------|-------------|-------------|---------------|
| Sequential |   1 |      3.1ms |      6.2ms |      **+51%** |         316 |         157 |      **+101%** |
| Light      |  20 |     44.1ms |     64.2ms |      **+31%** |         312 |         232 |       **+35%** |
| Medium     | 100 |    223.0ms |    257.6ms |      **+13%** |         298 |         254 |       **+18%** |
| Heavy      | 300 |    628.2ms |    734.5ms |      **+15%** |         323 |         253 |       **+28%** |

#### Streamable HTTP — I/O-bound async tool

| Load       |  c  | MiniMCP RT | FastMCP RT | RT Advantage | MiniMCP RPS | FastMCP RPS | RPS Advantage |
|------------|-----|------------|------------|--------------|-------------|-------------|---------------|
| Sequential |   1 |      5.0ms |      8.1ms |      **+39%** |         197 |         121 |       **+62%** |
| Light      |  20 |     47.1ms |     67.1ms |      **+30%** |         304 |         227 |       **+34%** |
| Medium     | 100 |    236.0ms |    266.0ms |      **+11%** |         284 |         248 |       **+14%** |
| Heavy      | 300 |    675.1ms |    751.5ms |      **+10%** |         302 |         247 |       **+22%** |

> 📝 **Streamable HTTP Headline**: Results are nearly identical to plain HTTP,
> confirming that the performance characteristics are driven by the MCP protocol
> layer rather than the specific HTTP framing.

---

## 💾 Memory Usage

MiniMCP's memory footprint is dramatically smaller and significantly more stable
under increasing load. FastMCP's memory grows substantially with concurrency;
MiniMCP's stays nearly flat.

### Peak memory usage at heavy load (c=300)

| Transport        | Workload  | MiniMCP | FastMCP | MiniMCP Advantage |
|------------------|-----------|---------|---------|-------------------|
| 📡 STDIO         | Sync      | 20.2 MB |  46.6 MB | **−57%** |
| 📡 STDIO         | Noop      | 20.1 MB |  46.4 MB | **−57%** |
| 📡 STDIO         | I/O-bound | 20.1 MB |  46.6 MB | **−57%** |
| 🌐 HTTP          | Sync      | 21.5 MB |  62.9 MB | **−66%** |
| 🌐 HTTP          | Noop      | 21.5 MB |  62.0 MB | **−65%** |
| 🌐 HTTP          | I/O-bound | 22.0 MB |  62.5 MB | **−65%** |
| 🌊 Streamable HTTP | Sync    | 22.1 MB |  62.9 MB | **−65%** |
| 🌊 Streamable HTTP | Noop    | 22.1 MB |  62.1 MB | **−64%** |
| 🌊 Streamable HTTP | I/O-bound | 22.1 MB | 62.5 MB | **−65%** |

FastMCP at heavy load consumes ~63 MB for HTTP transports and ~47 MB for STDIO,
while MiniMCP holds steady at ~22 MB and ~20 MB respectively. FastMCP's memory
grows with concurrency because its two-task-per-request architecture keeps more
in-flight state; MiniMCP's stateless single-task model grows barely at all.

---

## 📈 Summary Statistics

### ⏱️ Response Time: MiniMCP advantage over FastMCP

| Load Level  | 📡 STDIO         | 🌐 HTTP (Sync/Noop) | 🌐 HTTP (I/O-bound) |
|-------------|------------------|---------------------|---------------------|
| Sequential  | +28% to +53%     | +52% to +53%        | +39%                |
| Light       | +57% to +64%     | +31% to +38%        | +25% to +30%        |
| Medium      | +61% to +64%     | +13% to +19%        | +4% to +11%         |
| Heavy       | +62% to +64%     | +15% to +20%        | +10%                |

### 🚀 Throughput: MiniMCP advantage over FastMCP

| Load Level  | 📡 STDIO           | 🌐 HTTP (Sync/Noop) | 🌐 HTTP (I/O-bound) |
|-------------|--------------------|--------------------|---------------------|
| Sequential  | +38% to +107%      | +102% to +110%     | +62% to +63%        |
| Light       | +95% to +126%      | +34% to +46%       | +25% to +34%        |
| Medium      | +106% to +119%     | +17% to +25%       | +7% to +14%         |
| Heavy       | +113% to +115%     | +28% to +35%       | +22%                |

### 💾 Memory: MiniMCP advantage over FastMCP

| Load Level  | 📡 STDIO   | 🌐 HTTP transports |
|-------------|------------|--------------------|
| Sequential  | −47%       | −44%               |
| Light       | −48%       | −46% to −48%       |
| Medium      | −51%       | −53% to −54%       |
| Heavy       | **−57%**   | **−64% to −66%**   |

---

## 🏁 Conclusion

**🥇 MiniMCP is the clear winner** across all 36 test scenarios. The performance
profile differs by transport:

- 📡 **STDIO**: MiniMCP delivers a consistent 2× throughput advantage that does
  not erode with concurrency. For any stdio-based MCP deployment, the choice is
  unambiguous.

- 🌐 **HTTP / Streamable HTTP at low-to-medium concurrency**: MiniMCP's ~2× lower
  per-request cost translates directly into 38–53% faster response times. For
  typical production deployments (c ≤ 50), this is the most practically relevant
  range.

- ⚡ **HTTP / Streamable HTTP at high concurrency**: The advantage narrows to
  13–20% for noop/sync tools and 10–11% for I/O-bound tools. FastMCP partially
  closes the gap via better HTTP socket pipelining at high concurrency, but it
  never overtakes MiniMCP. With multiple uvicorn workers (the standard production
  deployment model) both servers scale linearly, and MiniMCP's advantage is
  unchanged.

- 💾 **Memory**: MiniMCP's 44–66% lower memory footprint is a consistent, large
  advantage that grows under load. This is a major factor for resource-constrained
  deployments or servers handling many concurrent connections.

**✅ Recommendation**: Use MiniMCP for all production deployments. The per-request
efficiency advantage is largest at low-to-medium concurrency (the common case),
holds meaningfully at high concurrency, and comes with a dramatically lower
memory footprint across all transport types and workloads.

---

*Generated from benchmark results dated 2026-03-21.*
*Benchmarks run on Linux 6.8.0-106-generic, Python 3.10.12, 24-core x86\_64, 62.6 GB RAM.*
