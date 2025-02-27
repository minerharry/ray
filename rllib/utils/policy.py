import gym
import logging
import re
from typing import Callable, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

import ray.cloudpickle as pickle
from ray.rllib.policy.policy import PolicySpec
from ray.rllib.policy.sample_batch import SampleBatch
from ray.rllib.utils.deprecation import Deprecated
from ray.rllib.utils.framework import try_import_tf
from ray.rllib.utils.typing import (
    ActionConnectorDataType,
    AgentConnectorDataType,
    AgentConnectorsOutput,
    PartialAlgorithmConfigDict,
    PolicyID,
    PolicyState,
    TensorStructType,
    TensorType,
)
from ray.util import log_once
from ray.util.annotations import PublicAPI

if TYPE_CHECKING:
    from ray.rllib.policy.policy import Policy

logger = logging.getLogger(__name__)

tf1, tf, tfv = try_import_tf()


@PublicAPI(stability="alpha")
def validate_policy_id(policy_id: str, error: bool = False) -> None:
    """Makes sure the given `policy_id` is valid.

    Args:
        policy_id: The Policy ID to check.
            IMPORTANT: Must not contain characters that
            are also not allowed in Unix/Win filesystems, such as: `<>:"/\\|?*`
            or a dot `.` or space ` ` at the end of the ID.
        error: Whether to raise an error (ValueError) or a warning in case of an
            invalid `policy_id`.

    Raises:
        ValueError: If the given `policy_id` is not a valid one and `error` is True.
    """
    if (
        not isinstance(policy_id, str)
        or len(policy_id) == 0
        or re.search('[<>:"/\\\\|?]', policy_id)
        or policy_id[-1] in (" ", ".")
    ):
        msg = (
            f"PolicyID `{policy_id}` not valid! IDs must be a non-empty string, "
            "must not contain characters that are also disallowed file- or directory "
            "names on Unix/Windows and must not end with a dot `.` or a space ` `."
        )
        if error:
            raise ValueError(msg)
        elif log_once("invalid_policy_id"):
            logger.warning(msg)


@PublicAPI
def create_policy_for_framework(
    policy_id: str,
    policy_class: "Policy",
    merged_config: PartialAlgorithmConfigDict,
    observation_space: gym.Space,
    action_space: gym.Space,
    worker_index: int = 0,
    session_creator: Optional[Callable[[], "tf1.Session"]] = None,
    seed: Optional[int] = None,
):
    """Frame specific policy creation logics.

    Args:
        policy_id: Policy ID.
        policy_class: Policy class type.
        merged_config: Complete policy config.
        observation_space: Observation space of env.
        action_space: Action space of env.
        worker_index: Index of worker holding this policy. Default is 0.
        session_creator: An optional tf1.Session creation callable.
        seed: Optional random seed.
    """
    from ray.rllib.algorithms.algorithm_config import AlgorithmConfig

    if isinstance(merged_config, AlgorithmConfig):
        merged_config = merged_config.to_dict()

    framework = merged_config.get("framework", "tf")
    # Tf.
    if framework in ["tf2", "tf"]:
        var_scope = policy_id + (f"_wk{worker_index}" if worker_index else "")
        # For tf static graph, build every policy in its own graph
        # and create a new session for it.
        if framework == "tf":
            with tf1.Graph().as_default():
                if session_creator:
                    sess = session_creator()
                else:
                    sess = tf1.Session(
                        config=tf1.ConfigProto(
                            gpu_options=tf1.GPUOptions(allow_growth=True)
                        )
                    )
                with sess.as_default():
                    # Set graph-level seed.
                    if seed is not None:
                        tf1.set_random_seed(seed)
                    with tf1.variable_scope(var_scope):
                        return policy_class(
                            observation_space, action_space, merged_config
                        )
        # For tf-eager: no graph, no session.
        else:
            with tf1.variable_scope(var_scope):
                return policy_class(observation_space, action_space, merged_config)
    # Non-tf: No graph, no session.
    else:
        return policy_class(observation_space, action_space, merged_config)


@PublicAPI(stability="alpha")
def parse_policy_specs_from_checkpoint(
    path: str,
) -> Tuple[PartialAlgorithmConfigDict, Dict[str, PolicySpec], Dict[str, PolicyState]]:
    """Read and parse policy specifications from a checkpoint file.

    Args:
        path: Path to a policy checkpoint.

    Returns:
        A tuple of: base policy config, dictionary of policy specs, and
        dictionary of policy states.
    """
    with open(path, "rb") as f:
        checkpoint_dict = pickle.load(f)
    # Policy data is contained as a serialized binary blob under their
    # ID keys.
    w = pickle.loads(checkpoint_dict["worker"])

    policy_config = w["policy_config"]
    assert policy_config.get("enable_connectors", False), (
        "load_policies_from_checkpoint only works for checkpoints generated by stacks "
        "with connectors enabled."
    )
    policy_states = w.get("policy_states", w["state"])
    serialized_policy_specs = w["policy_specs"]
    policy_specs = {
        id: PolicySpec.deserialize(spec) for id, spec in serialized_policy_specs.items()
    }

    return policy_config, policy_specs, policy_states


@PublicAPI(stability="alpha")
def local_policy_inference(
    policy: "Policy",
    env_id: str,
    agent_id: str,
    obs: TensorStructType,
) -> TensorStructType:
    """Run a connector enabled policy using environment observation.

    policy_inference manages policy and agent/action connectors,
    so the user does not have to care about RNN state buffering or
    extra fetch dictionaries.
    Note that connectors are intentionally run separately from
    compute_actions_from_input_dict(), so we can have the option
    of running per-user connectors on the client side in a
    server-client deployment.

    Args:
        policy: Policy.
        env_id: Environment ID.
        agent_id: Agent ID.
        obs: Env obseration.

    Returns:
        List of outputs from policy forward pass.
    """
    assert (
        policy.agent_connectors
    ), "policy_inference only works with connector enabled policies."

    # Put policy in inference mode, so we don't spend time on training
    # only transformations.
    policy.agent_connectors.in_eval()
    policy.action_connectors.in_eval()

    # TODO(jungong) : support multiple env, multiple agent inference.
    input_dict = {SampleBatch.NEXT_OBS: obs}
    acd_list: List[AgentConnectorDataType] = [
        AgentConnectorDataType(env_id, agent_id, input_dict)
    ]
    ac_outputs: List[AgentConnectorsOutput] = policy.agent_connectors(acd_list)
    outputs = []
    for ac in ac_outputs:
        policy_output = policy.compute_actions_from_input_dict(ac.data.sample_batch)

        action_connector_data = ActionConnectorDataType(
            env_id, agent_id, ac.data.raw_dict, policy_output
        )

        if policy.action_connectors:
            acd = policy.action_connectors(action_connector_data)
            actions = acd.output
        else:
            actions = policy_output[0]

        outputs.append(actions)

        # Notify agent connectors with this new policy output.
        # Necessary for state buffering agent connectors, for example.
        policy.agent_connectors.on_policy_output(action_connector_data)
    return outputs


@PublicAPI
def compute_log_likelihoods_from_input_dict(
    policy: "Policy", batch: Union[SampleBatch, Dict[str, TensorStructType]]
):
    """Returns log likelihood for actions in given batch for policy.

    Computes likelihoods by passing the observations through the current
    policy's `compute_log_likelihoods()` method

    Args:
        batch: The SampleBatch or MultiAgentBatch to calculate action
            log likelihoods from. This batch/batches must contain OBS
            and ACTIONS keys.

    Returns:
        The probabilities of the actions in the batch, given the
        observations and the policy.
    """
    num_state_inputs = 0
    for k in batch.keys():
        if k.startswith("state_in_"):
            num_state_inputs += 1
    state_keys = ["state_in_{}".format(i) for i in range(num_state_inputs)]
    log_likelihoods: TensorType = policy.compute_log_likelihoods(
        actions=batch[SampleBatch.ACTIONS],
        obs_batch=batch[SampleBatch.OBS],
        state_batches=[batch[k] for k in state_keys],
        prev_action_batch=batch.get(SampleBatch.PREV_ACTIONS),
        prev_reward_batch=batch.get(SampleBatch.PREV_REWARDS),
        actions_normalized=policy.config.get("actions_in_input_normalized", False),
    )
    return log_likelihoods


@Deprecated(new="Policy.from_checkpoint([checkpoint path], [policy IDs]?)", error=False)
def load_policies_from_checkpoint(
    path: str, policy_ids: Optional[List[PolicyID]] = None
) -> Dict[PolicyID, "Policy"]:

    return Policy.from_checkpoint(path, policy_ids)
