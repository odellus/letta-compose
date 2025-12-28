#!/usr/bin/env python3
"""Query Langfuse traces for Karla/Letta debugging.

Usage:
    python scripts/langfuse_traces.py                  # List recent traces
    python scripts/langfuse_traces.py <trace_id>       # Get specific trace details
    python scripts/langfuse_traces.py --search karla   # Search traces by name
    python scripts/langfuse_traces.py --last 5         # Show last N traces
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

# Load .env from repo root
from dotenv import load_dotenv
load_dotenv("/home/thomas/src/projects/letta-proj/.env")

# Langfuse config - use localhost since we're outside docker
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY")
# Convert docker internal host to localhost for direct access
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "").replace("host.docker.internal", "localhost")

if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
    print("Error: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set")
    print("Check /home/thomas/src/projects/letta-proj/.env")
    sys.exit(1)


def get_client():
    """Get Langfuse client."""
    from langfuse import Langfuse
    return Langfuse(
        public_key=LANGFUSE_PUBLIC_KEY,
        secret_key=LANGFUSE_SECRET_KEY,
        host=LANGFUSE_HOST,
    )


def list_traces(limit: int = 20, name_filter: str | None = None):
    """List recent traces."""
    langfuse = get_client()

    kwargs = {"limit": limit}
    if name_filter:
        kwargs["name"] = name_filter

    try:
        traces = langfuse.api.trace.list(**kwargs)

        print(f"{'ID':<40} {'Name':<30} {'Status':<10} {'Tokens':<10} {'Time'}")
        print("-" * 110)

        for trace in traces.data:
            trace_id = trace.id[:38] + ".." if len(trace.id) > 40 else trace.id
            name = (trace.name or "")[:28] + ".." if len(trace.name or "") > 30 else (trace.name or "-")
            status = getattr(trace, 'status', '-') or '-'

            # Get token usage
            usage = getattr(trace, 'usage', None)
            if usage:
                tokens = f"{usage.total_tokens}" if hasattr(usage, 'total_tokens') else "-"
            else:
                tokens = "-"

            # Format timestamp
            ts = trace.timestamp
            if ts:
                if isinstance(ts, str):
                    time_str = ts[:19]
                else:
                    time_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            else:
                time_str = "-"

            print(f"{trace_id:<40} {name:<30} {status:<10} {tokens:<10} {time_str}")

        print(f"\nTotal: {len(traces.data)} traces")
        return traces.data

    except Exception as e:
        print(f"Error fetching traces: {e}")
        return []


def get_trace(trace_id: str):
    """Get detailed trace information."""
    langfuse = get_client()

    try:
        trace = langfuse.api.trace.get(trace_id)

        print(f"Trace: {trace.id}")
        print(f"Name: {trace.name}")
        print(f"Status: {getattr(trace, 'status', '-')}")
        print(f"Timestamp: {trace.timestamp}")
        print(f"User ID: {getattr(trace, 'user_id', '-')}")
        print(f"Session ID: {getattr(trace, 'session_id', '-')}")

        # Metadata
        if hasattr(trace, 'metadata') and trace.metadata:
            print(f"\nMetadata:")
            for k, v in trace.metadata.items():
                print(f"  {k}: {v}")

        # Tags
        if hasattr(trace, 'tags') and trace.tags:
            print(f"\nTags: {', '.join(trace.tags)}")

        # Usage
        if hasattr(trace, 'usage') and trace.usage:
            usage = trace.usage
            print(f"\nToken Usage:")
            if hasattr(usage, 'input_tokens'):
                print(f"  Input: {usage.input_tokens}")
            if hasattr(usage, 'output_tokens'):
                print(f"  Output: {usage.output_tokens}")
            if hasattr(usage, 'total_tokens'):
                print(f"  Total: {usage.total_tokens}")

        # Observations (tool calls, generations, etc.)
        if hasattr(trace, 'observations') and trace.observations:
            print(f"\nObservations ({len(trace.observations)}):")
            for obs in trace.observations:
                obs_type = getattr(obs, 'type', 'UNKNOWN')
                obs_name = getattr(obs, 'name', '-')
                obs_status = getattr(obs, 'status', '-')
                print(f"  [{obs_type}] {obs_name} - {obs_status}")

                # Show input/output for generations
                if obs_type == 'GENERATION':
                    if hasattr(obs, 'input') and obs.input:
                        input_preview = str(obs.input)[:100]
                        print(f"    Input: {input_preview}...")
                    if hasattr(obs, 'output') and obs.output:
                        output_preview = str(obs.output)[:100]
                        print(f"    Output: {output_preview}...")

        return trace

    except Exception as e:
        print(f"Error fetching trace {trace_id}: {e}")
        return None


def get_observations(trace_id: str, obs_type: str | None = None):
    """Get observations for a trace."""
    langfuse = get_client()

    try:
        kwargs = {"trace_id": trace_id, "limit": 100}
        if obs_type:
            kwargs["type"] = obs_type

        observations = langfuse.api.observations.get_many(**kwargs)

        print(f"Observations for trace {trace_id}:")
        print(f"{'Type':<15} {'Name':<30} {'Status':<10} {'Duration':<10}")
        print("-" * 70)

        for obs in observations.data:
            obs_type = getattr(obs, 'type', 'UNKNOWN')
            obs_name = (getattr(obs, 'name', '-') or '-')[:28]
            obs_status = getattr(obs, 'status', '-') or '-'

            # Calculate duration
            start = getattr(obs, 'start_time', None)
            end = getattr(obs, 'end_time', None)
            if start and end:
                if isinstance(start, str):
                    duration = "-"
                else:
                    duration = f"{(end - start).total_seconds():.2f}s"
            else:
                duration = "-"

            print(f"{obs_type:<15} {obs_name:<30} {obs_status:<10} {duration:<10}")

        return observations.data

    except Exception as e:
        print(f"Error fetching observations: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Query Langfuse traces for Karla/Letta")
    parser.add_argument("trace_id", nargs="?", help="Specific trace ID to fetch")
    parser.add_argument("--search", "-s", help="Search traces by name")
    parser.add_argument("--last", "-n", type=int, default=20, help="Number of traces to show")
    parser.add_argument("--observations", "-o", action="store_true", help="Show observations for trace")
    parser.add_argument("--type", "-t", help="Filter observations by type (GENERATION, SPAN, etc.)")

    args = parser.parse_args()

    print(f"Langfuse: {LANGFUSE_HOST}")
    print()

    if args.trace_id:
        if args.observations:
            get_observations(args.trace_id, args.type)
        else:
            get_trace(args.trace_id)
    else:
        list_traces(limit=args.last, name_filter=args.search)


if __name__ == "__main__":
    main()
