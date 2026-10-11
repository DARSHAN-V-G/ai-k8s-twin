# Multi-Parameter Binary Search Engine

## 1. Mathematical Formulation

Rather than testing arbitrary static chaos values, the AI K8s Twin optimization engine searches the parameter space using binary search partitions:

$$\text{mid} = \frac{\text{Low} + \text{High}}{2}$$

For integer parameters:
$$\text{mid} = \lfloor \frac{\text{Low} + \text{High}}{2} \rfloor$$

If $\text{mid} == \text{Low}$ and $\text{Low} < \text{High}$, the search pushes forward by one unit:
$$\text{mid} = \text{Low} + 1$$

---

## 2. Active Search Bounds & Convergence Criteria

The engine maintains 4 concurrent parameter search sessions:

| Parameter | Unit | Lower Bound ($\text{Low}$) | Upper Bound ($\text{High}$) | Convergence Threshold ($\Delta = \text{High} - \text{Low}$) |
| :--- | :---: | :---: | :---: | :---: |
| **RAM (Memory Stress)** | M | $1\text{M}$ | Container limit or $2\times$ Request or node RAM | $\le 16\text{M}$ (or $\le 1\text{M}$ if no pass) |
| **CPU (CPU Stress)** | % | $10\%$ | $100\%$ | $\le 5\%$ |
| **DELAY (Network Delay)** | ms | $10\text{ms}$ | $1500\text{ms}$ | $\le 25\text{ms}$ |
| **LOSS (Network Loss)** | % | $0.5\%$ | $15.0\%$ | $\le 0.5\%$ |

---

## 3. Bound Updates & Step Progression

On each trial iteration:
- **If the Trial PASSED SLA**:
  - The system proved it survived at the tested stress levels.
  - The lower bounds advance to the tested values across all active sessions:
    $$\text{Low} = \text{Tested Value}$$
  - `best_passing_value` is updated to the tested value.
  - The step is logged: `"Raised Lower Bound: [Low, High] -> [NewLow, High] (Pushed stress higher)"`.

- **If the Trial BREACHED SLA**:
  - The failure attribution engine identifies the culprit parameter $C$.
  - **Only** the culprit's upper bound is contracted:
    $$\text{High}_C = \text{Tested Value}_C$$
  - All other 3 parameter sessions maintain their current bounds.
  - The step is logged: `"Contracted {C} Upper Bound: [Low, High] -> [Low, NewHigh] ({Reason}). Other dimensions held steady."`.

---

## 4. Downward Search Guarantee (Under-Provisioned Protection)

If a service is under-provisioned and breaches at all initial midpoints:
- Instead of aborting prematurely, the search continues downward until $\text{High} - \text{Low} \le 1\text{M}$ (or $0.5\%$).
- If no trial passes even at $1\text{M}$, `has_passed = False`, `max_safe_tolerance = 0M`, and the system flags the service as baseline under-provisioned, recommending a higher baseline memory request and limit.
