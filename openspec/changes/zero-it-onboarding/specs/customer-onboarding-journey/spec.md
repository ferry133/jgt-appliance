## ADDED Requirements

### Requirement: The customer performs exactly three physical actions

The customer's entire contribution SHALL be: unbox, connect the network cable, connect power and switch on. Anything else — imaging media, changing boot order, configuring a router, entering addresses, creating accounts — MUST be eliminated before delivery, not delegated to the customer.

#### Scenario: Nothing beyond three actions is asked
- **WHEN** the customer instructions are read end to end
- **THEN** they ask for unboxing, cabling, and power only

#### Scenario: Boot media is prepared before shipping
- **WHEN** hardware is delivered
- **THEN** it boots into the operating system from its internal disk without the customer selecting a boot device or entering firmware settings

#### Scenario: No network configuration is required
- **WHEN** the machine is connected to the customer's router
- **THEN** it obtains its address automatically and reaches the operator's management plane, with no router or device configuration

### Requirement: The customer knows what to expect at each point

Silence is indistinguishable from failure. The journey SHALL tell the customer what is happening, what is normal, and roughly how long it takes.

#### Scenario: Expected duration stated
- **WHEN** the customer completes the three physical actions
- **THEN** they are told what happens next and roughly how long it will take

#### Scenario: Normal intermediate states explained
- **WHEN** the system is in a state that could look like a fault
- **THEN** the customer has been told in advance that this state is normal

#### Scenario: Progress is pushed, not polled
- **WHEN** provisioning advances through its stages
- **THEN** the customer receives progress updates without having to check anything

### Requirement: The customer's inputs are collected before hardware arrives

Whatever the customer must supply SHALL be collected ahead of delivery, so that provisioning is not blocked waiting for an answer once the machine is online.

#### Scenario: Inputs collected in advance
- **WHEN** hardware ships
- **THEN** every customer-supplied value is already recorded against the work order

#### Scenario: Input set is minimal
- **WHEN** the customer is asked for information
- **THEN** they are asked only for what cannot be derived or supplied by the operator

### Requirement: Completion is delivered as something the customer can use

The journey ends with the customer able to reach their system, not with an internal status. Delivery SHALL include how to reach it and how to authenticate.

#### Scenario: Completion notice is actionable
- **WHEN** provisioning completes
- **THEN** the customer receives the address of their system and can authenticate using their own identity

#### Scenario: Customer authenticates as themselves
- **WHEN** the customer signs in to their system for the first time
- **THEN** they sign in with their own identity, not with a shared or operator-held credential

### Requirement: Failure gives the customer a next action, never a dead end

When something goes wrong the customer SHALL always have a defined next action, including a human to contact. A non-technical customer cannot be left to diagnose.

#### Scenario: Failure produces an instruction, not a diagnosis
- **WHEN** provisioning cannot proceed
- **THEN** the customer receives a concrete next action in non-technical language, not an error description

#### Scenario: Human escalation is always available
- **WHEN** the customer cannot resolve a situation through the guided steps
- **THEN** the instructions provide a way to reach a person

#### Scenario: On-site checks are expressed observably
- **WHEN** the customer is asked to check something physical
- **THEN** the check is expressed in terms they can observe directly, such as the colour of a light or whether a cable is seated
