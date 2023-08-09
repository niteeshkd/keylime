Use Measured Boot
=================

.. warning::
    This page is still under development and not complete. It will be so until
    this warning is removed.


Introduction
------------

In any real-world large-scale production environment, a large number of
different types of nodes will typically be found. The TPM 2.0 defines a
specific meaning - measurement of UEFI bios, measurement of boot device
firmware - for each of the lower-numbered PCRs (e.g., PCRs 0-9), as these are
extended during the multiple events of a measured boot log. However, simply
comparing the contents of these PCRs against a well-known "golden value"
becomes unfeasible. The reason for this is, in addition to the potentially
hundreds of variations due to node type, it can be experimentally demonstrated
that some PCRs (e.g, PCR 1) vary for each physical machine, if such machine is
netbooted (as it encodes the MAC address of the NIC used during boot.)

Fortunately, the UEFI firmware is now exposing the event log through an ACPI
table and a "recent enough" Linux kernel (e.g., 5.4 or later) is now consuming
this table and exposing this boot event log through the securityfs, typically
at the path `/sys/kernel/security/tpm0/binary_bios_measurements`. When combined
with `secure boot` and a "recent enough" version of grub (2.06 or later), the
aforementioned PCR set can be fully populated, including measurements of all
components, up to the `kernel` and `initrd`.

In addition to these sources of (boot log) data, a "recent enough" version of
`tpm2-tools` (5.0 or later) can be used to consume the contents of such logs
and thus rebuild the contents of PCRs [0-9] (and potentially PCRs [11-14]).

Implementation
--------------

Keylime can make use of this new capability in a very flexible manner. A
"measured boot reference state" or `mb_refstate` for short can be specified by
the `keylime` operator (i.e. the `tenant`). This operator-provided piece of
information is used, in a fashion similar to the "IMA policy" (previously known
as "allowlist"), by the `keylime_verifier`, to compare the contents of the
information shipped from the `keylime_agent` (boot log in one case, IMA log on
the other), against such reference state.

Due to the fact that physical node-specific information can be encoded on the
"measured boot log", it became necessary to specify (optionally) a second piece
of information, a "measured boot policy" or `mb_policy` . This information is
used to instruct the `keylime_verifier` on how to do the comparison (e.g.,
using a regular expression, rather than a simple equality match). The policy
name is specified in `keylime.conf`, under the `[cloud_verifier]` section of
the file, with parameter named `measured_boot_policy_name`. The default value
for it is `accept-all`, meaning "just don't try to match the contents, just
replay the log and make sure the values of PCRs [0-9] and [11-14] match".

Whenever a "measured boot reference state" is defined - via a new command-line
option in `keylime_tenant` - `--mb_refstate`, the following actions will be
taken.

1) PCRs [0-9] and [11-14] will be included in the quote sent by `keylime_agent`

2) The `keylime_agent` will also send the contents of
`/sys/kernel/security/tpm0/binary_bios_measurements`

3) The `keylime_verifier` will replay the boot log from step 2, ensuring the
correct values for PCRs collected in step 1. Again, this is very similar to
what it is done with "IMA logs" and PCR 10.

4) The very same `keylime_verifier` will take the boot log, now deemed
"attested" and compare it against the "measured boot reference state",
according to the "measured boot policy", causing the attestation to fail if it
does not conform.

How to use 
---------- 

The simplest way to use this new functionality is by
providing an empty "measured boot reference state" and an `accept-all`
"measured boot policy", which will cause the `keylime_verifier` to simply skip
the aforementioned step 4.

An example follows::

    echo "{}" > measured_boot_reference_state.txt

    keylime_tenant -c add -t <AGENT IP> -v <VERIFIER IP> -u <AGENT UUID> --mb_refstate ./measured_boot_reference_state.txt

Note: please keep in mind that the IMA-specific options can be combined with
the above options in the example, resulting in a configuration where a
`keylime_agent` sent a quote with PCRs [0-15] and both logs (boot and IMA)

Evidently, to be fully used in a meaningful manner, keylime operators need to
provide its own custom `mb_refstate` and `mb_policy`. While an user can write
a policy that performs an "exact match" on a carefully constructed refstate, the
key idea here is to create a pair of specification files which are at once meaningful
(for the purposes of trusted computing attestation) and generic (enough to be
applied to a set of nodes).

The most convenient way to crate an `mb_refstate` is starting from the contents
of an UEFI boot log from a given node, and then tweak and customize it to make
more generic. Keylime includes a tool (under `scripts` directory) -
`generate_mb_refstate` - which will consume a boot log and output a JSON file
containing an `mb_refstate`. An example follows::

   keylime/scripts/create_mb_refstate /sys/kernel/security/tpm0/binary_bios_measurements measured_boot_reference_state.json

   keylime_tenant -c add -t <AGENT IP> -v <VERIFIER IP> -u <AGENT UUID> --mb_refstate ./measured_boot_reference_state.json

This reference state can be (as in the example above) consumed "as is", or it
can be tweaked to be made more generic (or even more strict, if the keylime
operator chooses so).

The `mb_policy` is defined within a framework specified in `policies.py`, where
some "trivial" policies such as `accept-all` and `reject-all` are pre-defined.
The Domain-Specific Language (DSL) used by the framework are defined in
`tests.py` and an illustrative use of it can be seen in the policy
`example.py`, all under the `elchecking` directory. This example policy was
crafted to be meaningful (i.e., with a relevant number of parameters tests) and
yet applicable to a large set of nodes. It consumes a `mb_refstate` such as
the one generated by the aforementioned tool or the
`example_reference_state.json`, located under the same directory. 

Just to quickly exemplify what this policy does, it for instance tests if a
node has `SecureBoot` enabled (`tests.FieldTest("Enabled",
tests.StringEqual("Yes"))`) and if a node has a well-formed kernel command line
boot parameters (e.g., `tests.FieldTest("String",
tests.RegExp(r".*/grub.*"))`). The policy is well documented, and operators are
encouraged to just read through the comments in order to understand how the
tests are implemented.

While an operator can attempt to write its own policy from scratch, it is
recommended that one just copies `example.py` into `mypolicy.py`, change it as
required and then just points to this new policy on `keylime.conf`
(`measured_boot_policy_name`) for its own use.

Using OPA policy engine 
---------------------- 
Keylime, by default, uses elchecking policy engine (as explained above) to 
evaluate measured boot log for the specified policy and the refstate. In this
approach, the policy, specified using the verifier configuration item 
``measured_boot_policy_name`` in ``keylime.conf``, must be implemented in the module
specified with the verifier configuration item ``measured_boot_imports``. The policy
uses the refstate, passed with ``--mb_refstate`` option of the ``keylime_tenant`` command,
to evaluate the boot log and provides the result. In case of failure, it also 
provides the reasons of failure. If a new policy needs to be created or an existing policy
needs to be modified, the policy module would have to modified and then the 
verifier would have to be reconfigured and restarted for using the new/modified
policy.

Keylime provides `OPA <https://www.openpolicyagent.org/>`_ policy engine as an alternate option to evaluate the measured
boot log against a policy containing the refstate. In this approach, user provides
the policy for the refstate (using the same option i.e. ``--mb_refstate`` of the
``keylime_tenant`` command) and the OPA policy engine evaluates the boot log 
against the policy. The policy is written in `rego <https://www.openpolicyagent.org/docs/latest/policy-language/>`_ which is the query language
for OPA. In this case, user can easily create a new policy or modify an existing
one and use it without restarting the verifier. Currently, OPA policy engine 
interacts with an OPA server using REST API to evaluate the boot log. OPA server
could be run on the same node as verifier itself. 

To use OPA policy engine, user needs to specify 'keylime.mba.opa' for the
verifier configuration item ``measured_boot_imports`` and provide the info
(i.e. ip address, port and path of the certificate file for secure 
communication with SSL) about the OPA server using the verifier configuration
items ``opa_server_ip``, ``opa_server_port`` and ``opa_server_cert``. By default, the 
OPA server is expected to run on the same node as the verifier 
(i.e. ``opa_server_ip=127.0.0.1``), with its default port (i.e. ``opa_server_port=8181``)
and without the need of SSL communication.

After `downloading OPA <https://www.openpolicyagent.org/docs/latest/#running-opa>`_, one could start the OPA server as follows::

    opa run --server

If the SSL communication is needed, one needs to specify the path of certificate file to 
the verifier configuration item ``opa_server_cert`` and start the OPA server
by using the certificate with ``--tls-cert-file`` option as follows::

    opa run --server --tls-cert-file=<certificate> --tls-private-key-file=<private-key>

Once the OPA server and the verifier are started, user can pass the policy (say
mb-refstate-policy.rego) with ``--mb_refstate`` option of the ``keylime_tenant`` command as 
follows to evaluate the boot log while adding a node::

    keylime_tenant -c add -t <AGENT IP> -v <VERIFIER IP> -u <AGENT UUID> --mb_refstate ./mb-refstate-policy.rego

The policy file is required to have ``package`` name and an ``allow`` rule. Here is the
simplest example of a policy to always pass the evaluation (similar to ``accept_all``
policy defined with elchecking policy engine)::

    package mbpolicy1
    default allow := true

Following example shows how to use the refstate with the policy::

    package mbpolicy2
    import future.keywords.if

    refstate := {
        "kernel_authcode_sha256": "d968af6fbb6210352455d1c67b49d7b3c414361c9ea1d2828ef15f6d5bac4d19",
        "initrd_plain_sha256": "411a773dce24fddca247c8439182bf265504abb379be18f0f76df6ed3f575148"
    }

    # By default, do not allow.
    default allow := false

    # Allow only if the bootlog is validated succesfully against the refstate.
    allow {
        kernel_authcode_sha256_granted
        initrd_plain_sha256_granted
    }

    kernel_authcode_sha256_granted if {
        some i,j
        input.events[i].EventType == "EV_EFI_BOOT_SERVICES_APPLICATION"
        input.events[i].PCRIndex == 4
        input.events[i].Digests[j].AlgorithmId == "sha256"
        input.events[i].Digests[j].Digest == refstate.kernel_authcode_sha256
    }

    initrd_plain_sha256_granted if {
        some i,j
        input.events[i].EventType == "EV_IPL"
        input.events[i].PCRIndex == 9
        input.events[i].Digests[j].AlgorithmId == "sha256"
        input.events[i].Digests[j].Digest == refstate.initrd_plain_sha256
    }

    # If denied, return the reasons
    allow = denied {
        count(denied) > 0
    }

    denied[reason] {
        not initrd_plain_sha256_granted
        reason := "initrd_plain_sha256 is not valid."
    }

    denied[reason] {
        not kernel_authcode_sha256_granted
        reason := "kernel_authcode_sha256 is not valid."
    }

The above example also shows how to return the reasons of validation failure.
In the above example, the variable ``input`` represents the content of
measured boot log in json format. One could run the command ``tpm2_eventlog`` on the 
content of ``/sys/kernel/security/tpm0/binary_bios_measurements`` to get the measured boot
log which can be used to get the info (e.g. EventType, PCRIndex, Digests*)
about various events for creating a policy using refstate.
