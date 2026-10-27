"""Offline Gurobi reference with bounds and independently checked schedules."""

import math
import time

from .problem import PHASES, validate_plan


REFERENCE_VERSION = "queue-switch-events-v3-terminal"
CERT_TOLERANCE = 1e-6


class ReferenceSolver:
    def __init__(self, time_limit=120.0, environment=None):
        import gurobipy as gp
        if not math.isfinite(time_limit) or time_limit <= 0:
            raise ValueError("reference time limit must be positive and finite")
        self.gp = gp
        self.time_limit = time_limit
        self.owns_environment = environment is None
        self.environment = environment
        if self.environment is None:
            self.environment = gp.Env(empty=True)
            self.environment.setParam("OutputFlag", 0)
            self.environment.start()

    def close(self):
        if self.owns_environment:
            self.environment.dispose()

    def solve(self, instance, forced_first=None):
        if forced_first is not None and forced_first not in instance.legal_actions:
            raise ValueError("forced first action is illegal")
        gp, minimum = self.gp, instance.min_green
        clearance = instance.yellow + instance.all_red
        began = time.perf_counter()
        model = gp.Model("frozen_queue", env=self.environment)
        try:
            model.Params.TimeLimit = self.time_limit
            model.Params.Threads = 1
            model.Params.Seed = 0
            # Accumulated tolerance slack over long horizons must stay below
            # the independent scorer's absolute certification tolerance.
            model.Params.FeasibilityTol = 1e-9
            model.Params.IntFeasTol = 1e-9
            model.Params.MIPGap = 0
            model.Params.MIPGapAbs = CERT_TOLERANCE / 10
            h = instance.horizon
            # Compact event formulation, independent of the scorer's timers.
            # p is the most recently requested destination (1=NS). It is
            # integral from its initial value and binary directional changes.
            p = model.addVars(h, lb=0, ub=1)
            to_ns = model.addVars(h, vtype=gp.GRB.BINARY)
            to_ew = model.addVars(h, vtype=gp.GRB.BINARY)
            initial_target = instance.pending or instance.phase
            initial_p = int(initial_target == 'NS')
            first_switch = instance.remaining + minimum if instance.pending else max(0, minimum - instance.age)
            for t in range(h):
                model.addConstr(p[t] - (p[t - 1] if t else initial_p) == to_ns[t] - to_ew[t])
                # Successive switches need full clearance plus minimum green.
                model.addConstr(gp.quicksum(to_ns[k] + to_ew[k]
                    for k in range(max(0, t - clearance - minimum + 1), t + 1)) <= 1)
                if t < first_switch:
                    model.addConstr(to_ns[t] + to_ew[t] == 0)
            if forced_first is not None:
                model.addConstr(to_ns[0] + to_ew[0] == int(forced_first != instance.phase))
            queue = model.addVars(h + 1, 2, lb=0.0)
            served = model.addVars(h, 2, lb=0.0)
            for g, group in enumerate(PHASES):
                model.addConstr(queue[0, g] == instance.queues[g])
                switches_to = to_ns if group == 'NS' else to_ew
                switches_away = to_ew if group == 'NS' else to_ns
                for t in range(h):
                    active = p[t] if group == 'NS' else 1 - p[t]
                    clearing_to = gp.quicksum(switches_to[k] for k in range(max(0, t - clearance + 1), t + 1))
                    yellow_away = gp.quicksum(switches_away[k] for k in range(max(0, t - instance.yellow + 1), t + 1))
                    # Initial clearance is a switch before step zero; its cost
                    # is excluded but its service and remaining dwell apply.
                    if instance.pending == group and t < instance.remaining:
                        clearing_to += 1
                    if instance.pending and instance.phase == group and t < instance.remaining - instance.all_red:
                        yellow_away += 1
                    capacity = (instance.objective.green_capacity * (active - clearing_to)
                                + instance.objective.yellow_capacity * yellow_away)
                    model.addConstr(served[t, g] <= capacity)
                    available = queue[t, g] + instance.arrivals[t][g]
                    model.addConstr(served[t, g] <= available)
                    model.addConstr(queue[t + 1, g] == available - served[t, g])
            objective = gp.quicksum(queue[t, g] for t in range(1, h + 1) for g in range(2))
            objective += instance.objective.switch_penalty * gp.quicksum(to_ns[t] + to_ew[t] for t in range(h))
            objective += instance.objective.terminal_queue_penalty * gp.quicksum(queue[h, g] for g in range(2))
            model.setObjective(objective, gp.GRB.MINIMIZE)
            model.optimize()
            result = {
                "version": REFERENCE_VERSION, "forced_first": forced_first,
                "status": {gp.GRB.OPTIMAL: "optimal", gp.GRB.TIME_LIMIT: "time_limit",
                           gp.GRB.INFEASIBLE: "infeasible", gp.GRB.INTERRUPTED: "interrupted"}.get(model.Status, str(model.Status)),
                "solver_status": model.Status, "solver_version": list(gp.gurobi.version()),
                "time_limit_seconds": self.time_limit, "solve_seconds": model.Runtime,
                "feasibility_tolerance": model.Params.FeasibilityTol,
                "integrality_tolerance": model.Params.IntFeasTol,
                "wall_seconds": time.perf_counter() - began, "nodes": model.NodeCount,
                "variables": model.NumVars, "constraints": model.NumConstrs,
                "objective": None, "best_bound": model.ObjBound if math.isfinite(model.ObjBound) else None,
                "gap": None, "plan": None, "certified": False,
            }
            if model.SolCount:
                plan = []
                latest_switch = -clearance + instance.remaining if instance.pending else -clearance
                latest_target = initial_target
                for t in range(h):
                    if to_ns[t].X > 0.5 or to_ew[t].X > 0.5:
                        latest_switch = t
                        latest_target = 'NS' if to_ns[t].X > 0.5 else 'EW'
                        action = latest_target
                    elif t - latest_switch < clearance:
                        action = 'EW' if latest_target == 'NS' else 'NS'
                    else:
                        action = latest_target
                    plan.append(action)
                scored = validate_plan(instance, plan)
                if not scored["feasible"] or abs(scored["objective"] - model.ObjVal) > CERT_TOLERANCE:
                    raise RuntimeError("independent scorer disagrees with reference solution")
                result.update(objective=scored["objective"], plan=plan, gap=model.MIPGap)
                result["certified"] = (model.Status == gp.GRB.OPTIMAL and result["best_bound"] is not None
                                       and abs(scored["objective"] - result["best_bound"]) <= CERT_TOLERANCE)
            return result
        finally:
            model.dispose()

    def evaluate_actions(self, instance):
        solves = {action: self.solve(instance, action) for action in instance.legal_actions}
        uppers = [s["objective"] for s in solves.values() if s["objective"] is not None]
        lowers = [s["best_bound"] for s in solves.values()]
        certified = all(s["certified"] for s in solves.values())
        best = min(uppers) if uppers else None
        return {
            "actions": solves, "certified": certified,
            "objective": best, "best_bound": min(lowers) if all(x is not None for x in lowers) else None,
            "optimal_actions": [a for a, s in solves.items() if abs(s["objective"] - best) <= CERT_TOLERANCE]
                               if certified else [],
        }


def first_action_score(reference, action):
    if action not in reference["actions"]:
        return {"valid": False, "regret": None, "regret_lower": None, "regret_upper": None}
    chosen = reference["actions"][action]
    upper, lower = reference["objective"], reference["best_bound"]
    regret = chosen["objective"] - upper if reference["certified"] else None
    return {"valid": True, "regret": max(0.0, regret) if regret is not None else None,
            "regret_lower": max(0.0, chosen["best_bound"] - upper)
                            if chosen["best_bound"] is not None and upper is not None else None,
            "regret_upper": max(0.0, chosen["objective"] - lower)
                            if chosen["objective"] is not None and lower is not None else None,
            "optimal_action": action in reference["optimal_actions"] if reference["certified"] else None}
