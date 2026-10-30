# <Product name>: product spec

Owner: <name>. Date: <date>. Status: draft | agreed (<date>).

What a person can do and see, and why: not a technical design. The rules for each section are in
`references/spec-and-tickets.md`. An early error here spreads into every ticket, so keep the technical detail to
the decisions the owner made.

## Problem

<The problem, from the user's point of view, in one paragraph. Who has it.>

## Solution

<The solution, from the user's point of view.>

## User stories

<A long numbered list that covers every part of the feature:>
1. As a <actor>, I want <feature>, so that <benefit>.

## Implementation decisions

<The modules to build or change, their interfaces, schema changes, API contracts, the owner's technical rulings.
No file paths and no code.>

## Testing decisions

<What a good test is here (behaviour through a public interface). The seams the tests go through, each with a
one-line note on what it catches and what it misses. Similar tests in the repo to copy.>

## Rules it must keep

<The owner's rulings (decisions.md) and the project rules that this feature touches, one line each.>

## Out of scope

<What is left out on purpose, and where it may come later.>

## Done means

<How the owner checks it: the steps in the running product.>
