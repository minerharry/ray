# flake8: noqa E501

import copy
import json
import os
from dataclasses import dataclass

from typing import List


@dataclass
class Target:
    """Defines a Grafana target (time-series query) within a panel.

    A panel will have one or more targets. By default, all targets are rendered as
    stacked area charts, with the exception of legend="MAX", which is rendered as
    a blue dotted line.

    Attributes:
        expr: The prometheus query to evaluate.
        legend: The legend string to format for each time-series.
    """

    expr: str
    legend: str


@dataclass
class Panel:
    """Defines a Grafana panel (graph) for the Ray dashboard page.

    A panel contains one or more targets (time-series queries).

    Attributes:
        title: Short name of the graph. Note: please keep this in sync with the title
            definitions in Metrics.tsx.
        description: Long form description of the graph.
        id: Integer id used to reference the graph from Metrics.tsx.
        unit: The unit to display on the y-axis of the graph.
        targets: List of query targets.
    """

    title: str
    description: str
    id: int
    unit: str
    targets: List[Target]


METRICS_INPUT_ROOT = os.path.join(os.path.dirname(__file__), "export")
GRAFANA_CONFIG_INPUT_PATH = os.path.join(METRICS_INPUT_ROOT, "grafana")


GRAFANA_PANELS = [
    Panel(
        id=26,
        title="Scheduler Task State",
        description="Current number of tasks currently in a particular state.\n\nState: the task state, as described by rpc::TaskState proto in common.proto.",
        unit="tasks",
        targets=[
            Target(
                expr='sum(max_over_time(ray_tasks{State=~"FINISHED|FAILED"}[14d])) by (State) or clamp_min(sum(ray_tasks{State!~"FINISHED|FAILED"}) by (State), 0)',
                legend="{{State}}",
            )
        ],
    ),
    Panel(
        id=35,
        title="Active Tasks by Name",
        description="Current number of (live) tasks with a particular name.",
        unit="tasks",
        targets=[
            Target(
                expr='sum(ray_tasks{State!~"FINISHED|FAILED"}) by (Name)',
                legend="{{Name}}",
            )
        ],
    ),
    Panel(
        id=33,
        title="Scheduler Actor State",
        description="Current number of actors currently in a particular state.\n\nState: the actor state, as described by rpc::ActorTableData proto in gcs.proto.",
        unit="actors",
        targets=[
            Target(
                expr="sum(ray_actors) by (State)",
                legend="{{State}}",
            )
        ],
    ),
    Panel(
        id=36,
        title="Active Actors by Name",
        description="Current number of (live) actors with a particular name.",
        unit="actors",
        targets=[
            Target(
                expr="sum(ray_actors) by (Name)",
                legend="{{Name}}",
            )
        ],
    ),
    Panel(
        id=27,
        title="Scheduler CPUs (logical slots)",
        description="Logical CPU usage of Ray. The dotted line indicates the total number of CPUs. The logical CPU is allocated by `num_cpus` arguments from tasks and actors. \n\nNOTE: Ray's logical CPU is different from physical CPU usage. Ray's logical CPU is allocated by `num_cpus` arguments.",
        unit="cores",
        targets=[
            Target(
                expr='sum(ray_resources{Name="CPU",State="USED"}) by (instance)',
                legend="CPU Usage: {{instance}}",
            ),
            Target(
                expr='sum(ray_resources{Name="CPU"})',
                legend="MAX",
            ),
        ],
    ),
    Panel(
        id=29,
        title="Object Store Memory",
        description="The physical (hardware) memory usage for each node. The dotted line means the total amount of memory from the cluster. Node memory is a sum of object store memory (shared memory) and heap memory.\n\nNote: If Ray is deployed within a container, the total memory could be lower than the host machine because Ray may reserve some additional memory space outside the container.",
        unit="gbytes",
        targets=[
            Target(
                expr="sum(ray_object_store_memory / 1e9) by (Location)",
                legend="{{Location}}",
            ),
            Target(
                expr='sum(ray_resources{Name="object_store_memory"} / 1e9)',
                legend="MAX",
            ),
        ],
    ),
    Panel(
        id=28,
        title="Scheduler GPUs (logical slots)",
        description="Logical GPU usage of Ray. The dotted line indicates the total number of GPUs. The logical GPU is allocated by `num_gpus` arguments from tasks and actors. ",
        unit="GPUs",
        targets=[
            Target(
                expr='ray_resources{Name="GPU",State="USED"}',
                legend="GPU Usage: {{instance}}",
            ),
            Target(
                expr='sum(ray_resources{Name="GPU"})',
                legend="MAX",
            ),
        ],
    ),
    Panel(
        id=2,
        title="Node CPU (hardware utilization)",
        description="",
        unit="cores",
        targets=[
            Target(
                expr='ray_node_cpu_utilization{instance=~"$Instance",cluster_id="$cluster_id"} * ray_node_cpu_count{instance=~"$Instance",cluster_id="$cluster_id"} / 100',
                legend="CPU Usage: {{instance}}",
            ),
            Target(
                expr='sum(ray_node_cpu_count{cluster_id="$cluster_id"})',
                legend="MAX",
            ),
        ],
    ),
    Panel(
        id=8,
        title="Node GPU (hardware utilization)",
        description="Node's physical (hardware) GPU usage. The dotted line means the total number of hardware GPUs from the cluster. ",
        unit="GPUs",
        targets=[
            Target(
                expr='ray_node_gpus_utilization{instance=~"$Instance",cluster_id="$cluster_id"} / 100',
                legend="GPU Usage: {{instance}}",
            ),
            Target(
                expr='sum(ray_node_gpus_available{cluster_id="$cluster_id"})',
                legend="MAX",
            ),
        ],
    ),
    Panel(
        id=6,
        title="Node Disk",
        description="Node's physical (hardware) disk usage. The dotted line means the total amount of disk space from the cluster.\n\nNOTE: When Ray is deployed within a container, this shows the disk usage from the host machine. ",
        unit="bytes",
        targets=[
            Target(
                expr='ray_node_disk_usage{instance=~"$Instance",cluster_id="$cluster_id"}',
                legend="Disk Used: {{instance}}",
            ),
            Target(
                expr='sum(ray_node_disk_free{cluster_id="$cluster_id"}) + sum(ray_node_disk_usage{cluster_id="$cluster_id"})',
                legend="MAX",
            ),
        ],
    ),
    Panel(
        id=32,
        title="Node Disk IO Speed",
        description="Disk IO per node.",
        unit="Bps",
        targets=[
            Target(
                expr='ray_node_disk_io_write_speed{instance=~"$Instance",cluster_id="$cluster_id"}',
                legend="Write: {{instance}}",
            ),
            Target(
                expr='ray_node_disk_io_read_speed{instance=~"$Instance",cluster_id="$cluster_id"}',
                legend="Read: {{instance}}",
            ),
        ],
    ),
    Panel(
        id=4,
        title="Node Memory (heap + object store)",
        description="The physical (hardware) memory usage for each node. The dotted line means the total amount of memory from the cluster. Node memory is a sum of object store memory (shared memory) and heap memory.\n\nNote: If Ray is deployed within a container, the total memory could be lower than the host machine because Ray may reserve some additional memory space outside the container.",
        unit="bytes",
        targets=[
            Target(
                expr='ray_node_mem_used{instance=~"$Instance",cluster_id="$cluster_id"}',
                legend="Memory Used: {{instance}}",
            ),
            Target(
                expr='sum(ray_node_mem_total{cluster_id="$cluster_id"})',
                legend="MAX",
            ),
        ],
    ),
    Panel(
        id=34,
        title="Node Memory by Component",
        description="The physical (hardware) memory usage across the cluster, broken down by component. This reports the summed USS (unique set size) per Ray component.",
        unit="bytes",
        targets=[
            Target(
                expr="sum(ray_component_uss_mb * 1e6) by (Component)",
                legend="{{Component}}",
            )
        ],
    ),
    Panel(
        id=18,
        title="Node GPU Memory (GRAM)",
        description="The physical (hardware) GPU memory usage for each node. The dotted line means the total amount of GPU memory from the cluster.",
        unit="bytes",
        targets=[
            Target(
                expr='ray_node_gram_used{instance=~"$Instance",cluster_id="$cluster_id"} * 1024 * 1024',
                legend="Used GRAM: {{instance}}",
            ),
            Target(
                expr='(sum(ray_node_gram_available{cluster_id="$cluster_id"}) + sum(ray_node_gram_used{cluster_id="$cluster_id"})) * 1024 * 1024',
                legend="MAX",
            ),
        ],
    ),
    Panel(
        id=20,
        title="Node Network",
        description="Network speed per node",
        unit="Bps",
        targets=[
            Target(
                expr='ray_node_network_receive_speed{instance=~"$Instance",cluster_id="$cluster_id"}',
                legend="Recv: {{instance}}",
            ),
            Target(
                expr='ray_node_network_send_speed{instance=~"$Instance",cluster_id="$cluster_id"}',
                legend="Send: {{instance}}",
            ),
        ],
    ),
    Panel(
        id=24,
        title="Node Count",
        description="A total number of active failed, and pending nodes from the cluster. \n\nACTIVE: A node is alive and available.\n\nFAILED: A node is dead and not available. The node is considered dead when the raylet process on the node is terminated. The node will get into the failed state if it cannot be provided (e.g., there's no available node from the cloud provider) or failed to setup (e.g., setup_commands have errors). \n\nPending: A node is being started by the Ray cluster launcher. The node is unavailable now because it is being provisioned and initialized.",
        unit="nodes",
        targets=[
            Target(
                expr='ray_cluster_active_nodes{cluster_id="$cluster_id"}',
                legend="Active Nodes: {{node_type}}",
            ),
            Target(
                expr='ray_cluster_failed_nodes{cluster_id="$cluster_id"}',
                legend="Failed Nodes: {{node_type}}",
            ),
            Target(
                expr='ray_cluster_pending_nodes{cluster_id="$cluster_id"}',
                legend="Pending Nodes: {{node_type}}",
            ),
        ],
    ),
]


TARGET_TEMPLATE = {
    "exemplar": True,
    "expr": "0",
    "interval": "",
    "legendFormat": "",
    "queryType": "randomWalk",
    "refId": "A",
}


PANEL_TEMPLATE = {
    "aliasColors": {},
    "bars": False,
    "dashLength": 10,
    "dashes": False,
    "datasource": "Prometheus",
    "description": "<Description>",
    "fieldConfig": {"defaults": {}, "overrides": []},
    "fill": 10,
    "fillGradient": 0,
    "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
    "hiddenSeries": False,
    "id": 26,
    "legend": {
        "alignAsTable": True,
        "avg": False,
        "current": True,
        "hideEmpty": False,
        "hideZero": True,
        "max": False,
        "min": False,
        "rightSide": False,
        "show": True,
        "sort": "current",
        "sortDesc": True,
        "total": False,
        "values": True,
    },
    "lines": True,
    "linewidth": 1,
    "nullPointMode": "null",
    "options": {"alertThreshold": True},
    "percentage": False,
    "pluginVersion": "7.5.17",
    "pointradius": 2,
    "points": False,
    "renderer": "flot",
    "seriesOverrides": [
        {
            "$$hashKey": "object:2987",
            "alias": "MAX",
            "dashes": True,
            "color": "#1F60C4",
            "fill": 0,
            "stack": False,
        }
    ],
    "spaceLength": 10,
    "stack": True,
    "steppedLine": False,
    "targets": [],
    "thresholds": [],
    "timeFrom": None,
    "timeRegions": [],
    "timeShift": None,
    "title": "<Title>",
    "tooltip": {"shared": True, "sort": 0, "value_type": "individual"},
    "type": "graph",
    "xaxis": {
        "buckets": None,
        "mode": "time",
        "name": None,
        "show": True,
        "values": [],
    },
    "yaxes": [
        {
            "$$hashKey": "object:628",
            "format": "units",
            "label": "",
            "logBase": 1,
            "max": None,
            "min": "0",
            "show": True,
        },
        {
            "$$hashKey": "object:629",
            "format": "short",
            "label": None,
            "logBase": 1,
            "max": None,
            "min": None,
            "show": True,
        },
    ],
    "yaxis": {"align": False, "alignLevel": None},
}


def generate_grafana_dashboard() -> str:
    base_json = json.load(
        open(
            os.path.join(
                GRAFANA_CONFIG_INPUT_PATH, "dashboards", "grafana_dashboard_base.json"
            )
        )
    )
    base_json["panels"] = _generate_grafana_panels()
    return json.dumps(base_json, indent=4)


def _generate_grafana_panels() -> List[dict]:
    panels = []
    for i, panel in enumerate(GRAFANA_PANELS):
        template = copy.deepcopy(PANEL_TEMPLATE)
        template.update(
            {
                "title": panel.title,
                "description": panel.description,
                "id": panel.id,
                "targets": _generate_targets(panel),
            }
        )
        template["gridPos"]["y"] = i // 2
        template["gridPos"]["x"] = 12 * (i % 2)
        template["yaxes"][0]["format"] = panel.unit
        panels.append(template)
    return panels


def _generate_targets(panel: Panel) -> List[dict]:
    targets = []
    for target, ref_id in zip(panel.targets, ["A", "B", "C", "D"]):
        template = copy.deepcopy(TARGET_TEMPLATE)
        template.update(
            {
                "expr": target.expr,
                "legendFormat": target.legend,
                "refId": ref_id,
            }
        )
        targets.append(template)
    return targets
