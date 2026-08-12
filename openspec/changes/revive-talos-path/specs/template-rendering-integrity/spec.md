## ADDED Requirements

### Requirement: Every data source a template reads is declared

Templates read values from declared data files. A template referencing values from an undeclared source renders empty or fails in ways that are hard to trace. Every data source SHALL be declared in the rendering configuration.

#### Scenario: Node data is declared
- **WHEN** templates reference per-node values
- **THEN** the node configuration file is among the declared data sources

#### Scenario: Undeclared source is a defect
- **WHEN** a template references a value from a file that is not a declared data source
- **THEN** that is treated as a defect to fix, not worked around at render time

### Requirement: Task definitions contain no undefined variables

A task referencing a variable that is defined nowhere fails at run time with an unhelpful message. Every variable a task references SHALL be defined.

#### Scenario: No dangling variable references
- **WHEN** task definitions are checked
- **THEN** every referenced variable resolves to a definition

#### Scenario: Task definitions remain parseable
- **WHEN** the task list is requested
- **THEN** every task file parses and every defined task is listed

### Requirement: Inherited tasks that do not apply are removed

This repository was derived from an upstream template and inherited tasks written for a different lifecycle. A per-user cluster repository never graduates from templating — its configuration is re-rendered for the life of the cluster. Inherited tasks whose premise does not hold here SHALL be removed rather than left runnable, because running one destroys the repository's ability to re-render.

#### Scenario: Graduation task is absent
- **WHEN** the available tasks are listed
- **THEN** no task exists that archives or removes the templating machinery

#### Scenario: Re-rendering always remains possible
- **WHEN** any task in this repository is run
- **THEN** the ability to re-run configuration rendering is preserved

#### Scenario: Removal is explained where it was
- **WHEN** a reader looks for the inherited task
- **THEN** a note records that it was removed and why, so it is not reintroduced from upstream

### Requirement: A field has one effective default

A field SHALL NOT have one default declared in schema validation and a different default applied during rendering. Divergent defaults mean the value a user sees documented is not the value the system uses.

#### Scenario: Defaults agree
- **WHEN** a field's schema default and its render-time default are compared
- **THEN** they are the same value, or exactly one of the two exists

#### Scenario: Path-dependent defaults are expressed as such
- **WHEN** the correct default for a field differs between provisioning paths
- **THEN** the difference is expressed explicitly per path, rather than one default silently overriding the other

#### Scenario: Documented default matches behaviour
- **WHEN** a sample configuration file documents a field's default
- **THEN** omitting that field produces the documented value

### Requirement: Rendering integrity is checkable

These properties SHALL be verifiable by running a check, not only by reading the files, so that regressions are caught rather than rediscovered later.

#### Scenario: Check detects a dangling variable
- **WHEN** a task is given a reference to an undefined variable
- **THEN** the check fails and names it

#### Scenario: Check detects divergent defaults
- **WHEN** a field's schema default and render-time default are made to disagree
- **THEN** the check fails and names the field
