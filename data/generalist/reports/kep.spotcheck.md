# kep: 20 random items for a spot check

Check the gold label against the linked source record.

## 1. KEP-3156 (train): gold = Did not go ahead as proposed: withdrawn, rejected, replaced by another KEP, or deferred

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-api-machinery/3156-http3/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-api-machinery, created 2022-01-13)
Title: HTTP3
Summary: One of the main advantages of HTTP/3 is increased performance, specifically around fetching multiple objects simultaneously. With HTTP/2, any interruption (packet loss) in the TCP connection blocks all streams (Head of line blocking). In addition, HTTP/3 offers 0-RTT support, which means that subsequent connections can start up much faster by eliminating the TLS acknowledgement from the server when setting up the connection. This means the client can start requesting data much faster than with a full TLS negotiation.

What became of this enhancement proposal?
```

## 2. KEP-2876 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-api-machinery/2876-crd-validation-expression-language/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-api-machinery, created 2021-05-26)
Title: CRD Validation Expression Language
Summary: CRDs need direct support for non-trivial validation. While admission webhooks do support CRDs validation, they significantly complicate the development and operability of CRDs. This KEP proposes that an inline expression language be integrated directly into CRDs such that a much larger portion of validation use cases can be solved without the use of webhooks. This KEP proposes the adoption of Common Expression Language (CEL). It is sufficiently lightweight and safe to be run directly in the kube-apiserver (since CRD creation is a privileged operation), has a straight-forward and unsurprising grammar, and supports pre-parsing and typechecking of expressions, allowing syntax and type errors to be caught at CRD registration time. CEL might be used in Kubernetes for extensibility beyond CRD validation.

What became of this enhancement proposal?
```

## 3. KEP-3017 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-apps/3017-pod-healthy-policy-for-pdb/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-apps, created 2021-10-24)
Title: Pod Healthy Policy for PDB
Summary: Pod Disruption Budgets currently don't provide a way for users to specify how to handle pods that are Running, but not Healthy (Ready). In this KEP, we add a new field `unhealthyPodEvictionPolicy` that allows users to specify what should happen to these not Healthy (Ready) pods. Whether they should be always evicted or kept in case the application guarded by a Pod Disruption Budget is not available and disrupted.

Which of these describes the outcome of this KEP?
```

## 4. KEP-1205 (test): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-auth/1205-bound-service-account-tokens/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-auth, created 2019-08-06)
Title: Bound Service Account Tokens
Summary: This KEP describes an API that would allow workloads running on Kubernetes to request JSON Web Tokens that are audience, time and eventually key bound. In addition, this KEP introduces a new mechanism of distribution with support for bound service account tokens and explores how to migrate from the existing mechanism backwards compatibly.

How did this Kubernetes enhancement proposal end?
```

## 5. KEP-4247 (select): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-scheduling/4247-queueinghint/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-scheduling, created 2023-09-30)
Title: Per-plugin callback functions for efficient requeueing in the scheduling queue
Summary: The scheduler gets a new functionality called `QueueingHint` to get suggestion for how to requeue Pods from each plugin. It helps reducing useless scheduling retries and thus improving the scheduling throughput. Also, by giving an ability to skip backoff in appropriate cases, the time to take to schedule Pods with dynamic resource allocation is improved.

Where did this Kubernetes enhancement proposal end up?
```

## 6. KEP-4193 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-auth/4193-bound-service-account-token-improvements/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-auth, created 2023-08-02)
Title: bound service account token improvements
Summary: Token projection and alternative audiences on JWTs issued by the apiserver enable an external entity to validate the identity and certain properties (e.g. associated ServiceAccount or Pod) of the caller. When attempting to verify a token associated with a Pod, it is not possible to verify that the Pod is associated with a specific Node without `get`ing the relevant Pod object (embedded as a private claim in the JWT) and cross-referencing the named `spec.nodeName`. To allow for a robust chain of identity verification from the requester all the way through to the projected token, it would be beneficial if the Node object reference associated with the requesting Pod were embedded into the signed JWT. This is especially useful in cases where the external software wants to avoid replay attacks with projected service account tokens.

How did this Kubernetes enhancement proposal end?
```

## 7. KEP-2332 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-api-machinery/2332-pruning-for-custom-resources/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-api-machinery, created 2018-07-31)
Title: Pruning for Custom Resources
Summary: CustomResources store arbitrary JSON data without following the typical Kubernetes API behaviour to prune unknown fields. This makes CRDs different, but also leads to security and general data consistency concerns because it is unclear what is actually stored in etcd. This KEP proposes to add pruning of all fields which are not specified in the OpenAPI validation schemas given in the CRD. Pruning will be opt-in in v1beta1 of `apiextensions.k8s.io` via. i.e. CRDs created in v1beta1 default to disabled pruning. Pruning will be enabled for every CRD created in v1 and we will hide `preserveUnknownFields` in v1 in that case. Pruning can be disabled for subtrees of CustomResources by setting the `x-kubernetes-preserve-unknown-fields: true` vendor extension. This allows to store arbitrary JSON or RawExtensions. This will even be possible at the root level, even in v1.

How did this Kubernetes enhancement proposal end?
```

## 8. KEP-2290 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-testing/2290-new-label-for-trusted-PR-identification/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-testing, created 2018-06-25)
Title: New label for trusted PR identification
Summary: This document describes a major change to the way the `trigger` plugin determines if test jobs should be started on a pull request (PR). We propose introducing a new label named `ok-to-test` that will be applied on non-member PRs once they have been `/ok-to-test` by a legitimate reviewer.

What is the final status of this Kubernetes enhancement proposal?
```

## 9. KEP-2214 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-apps/2214-indexed-job/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-apps, created 2020-12-29)
Title: Indexed Job
Summary: This KEP extends kubernetes with user-friendly support for running parallel jobs. Here, parallel means multiple pods per Job. Jobs can be: Embarrassingly parallel, where the pods have no dependencies between each other. Tightly coupled, where the Pods communicate among themselves to make progress kubernetes/kubernetes#99497. We propose the addition of completion indexes into the Pods of a Job [with fixed completion count] to support running embarrassingly parallel programs, with a focus on ease of use for workload partitioning. We call this new Job pattern an Indexed Job, because each Pod of the Job specializes to work on a particular index, as if the Pods where elements of an array. With the addition of a headless Service, Pods can address another Pod with a specific index with a DNS lookup, because the index is part of the hostname.

What is the final status of this Kubernetes enhancement proposal?
```

## 10. KEP-2200 (test): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-network/2200-externalips-admission/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-network, created 2020-12-07)
Title: Block ExternalIPs via Admission Control
Summary: This proposal is in response to CVE-2020-8554: "Man in the middle using LoadBalancer or ExternalIPs". Fundamentally the `Service.spec.externalIPs[]` feature is bad. It predates `Service.spec.type=LoadBalancer` and, now that we have that, has very few use-cases. In short an unprivileged user can hijack an IP address via a Service spec. In contrast, `type=LoadBalancer` uses Service status, which most normal users should not be allowed to write. This KEP proposes to block the use of ExternalIPs via a built-in admission controller. The justification for this, as opposed to a webhook, is that 99% of users will never use this feature, and making them ALL run a webhook seems terrible.

What became of this enhancement proposal?
```

## 11. KEP-121 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-storage/121-local-persistent-volumes/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-storage, created 2019-01-24)
Title: Local Persistent Volumes
Summary: This document presents a detailed design for supporting persistent local storage, as outlined in Local Storage Overview. This KEP replaces the original design proposal and has been updated to reflect the current implementation.

What became of this enhancement proposal?
```

## 12. KEP-5004 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-scheduling/5004-dra-extended-resource/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-scheduling, created 2025-02-03)
Title: DRA Extended Resource
Summary: Extended resource provides a simple, concise approach to describe resource capacity, and resource consumption. In constrast, Dynamic Resource Allocation (DRA) provides a more expressive, flexible approach, yet more complicated, and harder to use. This KEP provides a solution to enable cluster administrators to advertise the dynamic resources (in `ResourceSlice`) as extended resource via `DeviceClass`. and enables the application developers, and operators to continue using extended resource to request for such resources. This KEP provides dynamic allocation of resources to requests made through either extended resource, or DRA resource claim.

What is the final status of this Kubernetes enhancement proposal?
```

## 13. KEP-689 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-windows/689-windows-gmsa/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-windows, created 2018-11-29)
Title: Windows Group Managed Service Accounts for Container Identity
Summary: Active Directory is a service that is built-in and commonly used on Windows Server deployments for user and computer identity. Apps are run using Active Directory identities to enable common user to service, and service to service authentication and authorization. This proposal aims to support a specific type of identity, Group Managed Service Accounts (GMSA), for use with Windows Server containers. This will allow an operator to choose a GMSA at deployment time, and run containers using it to connect to existing applications such as a database or API server without changing how the authentication and authorization are performed.

How did this Kubernetes enhancement proposal end?
```

## 14. KEP-5080 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-api-machinery/5080-ordered-namespace-deletion/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-api-machinery, created 2024-01-27)
Title: Ordered Namespace Deletion
Summary: This kep introduces an opinionated deletion process in the Kubernetes namespace deletion to ensure secure deletion of resources within a namespace. The current deletion process is semi-random, which may lead to security gaps or unintended behavior, such as Pods persisting after the deletion of their associated NetworkPolicies. By implementing an opinionated deletion mechanism, the Pods will be deleted before other resources with respects logical and security dependencies. This design enhances the security and reliability of Kubernetes by mitigating risks arising from the non-deterministic deletion order.

What became of this enhancement proposal?
```

## 15. KEP-2317 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-storage/2317-fsgroup-on-mount/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-storage, created 2021-01-22)
Title: Provide fsgroup of pod to CSI driver on mount
Summary: Currently for most volume plugins kubelet applies fsgroup ownership and permission-based changes by recursively `chown`ing and `chmod`ing the files and directories inside a volume. For certain CSI drivers this may not be possible because `chown` and `chmod` are unix primitives and underlying CSI driver may not support them. This enhancement proposes providing the CSI driver with fsgroup as an explicit field so as CSI driver can apply this on mount time.

Where did this Kubernetes enhancement proposal end up?
```

## 16. KEP-3983 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-node/3983-drop-in-configuration/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-node, created 2023-05-04)
Title: Add support for a kubelet drop-in configuration directory
Summary: A common pattern for software configuration in linux is support for a drop-in configuration directory. The location of this directory is often based on a corresponding configuration file. For instance, `/etc/security/limits` can be overridden by files in `/etc/security/limits.d`. This pattern is useful for a number of reasons, though a large motivation here is to allow files to be owned by a single owner. If multiple processes are vying for changing the same file, then they could stamp over each other's changes and possibly race against each other, creating TOCTOU problems. Components in Kubernetes can similarly be configured by multiple entities and preventing races between them is cumbersome. There has been past work in the Kubelet to have a Dynamic Configuration, but resolving between multiple entities and a last known good state was also complicated.

What became of this enhancement proposal?
```

## 17. KEP-5100 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-windows/5100-windows-dsr-and-overlay-support/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-windows, created 2025-01-28)
Title: DSR and Overlay support in Windows kube-proxy
Summary: Add support for DSR (Direct Server Return) and Overlay networking mode support for Windows kube-proxy.

Which of these describes the outcome of this KEP?
```

## 18. KEP-3756 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-storage/3756-volume-reconstruction/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-storage, created 2023-01-20)
Title: Robust VolumeManager reconstruction after kubelet restart
Summary: After kubelet is restarted, it looses track of all volume it mounted for running Pods. It tries to restore this state from the API server, where kubelet can find Pods that should be running, and from the host's OS, where it can find actually mounted volumes. We know this process is imperfect. This KEP tries to rework the process. While the work is technically a bugfix, it changes large parts of kubelet, and we'd like to have it behind a feature gate to provide users a way to get to the old implementations in case of problems.

Where did this Kubernetes enhancement proposal end up?
```

## 19. KEP-3545 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-node/3545-improved-multi-numa-alignment/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-node, created 2022-09-26)
Title: Improved multi-numa alignment in Topology Manager
Summary: We propose an enhancement to the `TopologyManager` that allows it to favor sets of NUMA nodes with shorter distance between nodes when making admission decisions. The proposed enhancement is only applicable when comparing sets of NUMA nodes that are equal in size.

Which of these describes the outcome of this KEP?
```

## 20. KEP-2799 (train): gold = Implemented: the enhancement was completed

https://github.com/kubernetes/enhancements/blob/ea3e81a0d41dd3df7dae584ea584c31de56cd3cb/keps/sig-auth/2799-reduction-of-secret-based-service-account-token/README.md

```
Kubernetes enhancement proposal (owning SIG: sig-auth, created 2021-06-25)
Title: Reduction of Secret-based Service Account Tokens
Summary: This KEP proposes actions to reduce the surface area of secret-based service account tokens.

What became of this enhancement proposal?
```

