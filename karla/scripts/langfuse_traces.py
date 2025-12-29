#!/usr/bin/env python3
"""Query Langfuse traces for Karla/Letta debugging.

Usage:
    python scripts/langfuse_traces.py                  # List recent traces
    python scripts/langfuse_traces.py <trace_id>       # Get specific trace details
    python scripts/langfuse_traces.py <trace_id> -o    # List observations
    python scripts/langfuse_traces.py <trace_id> --llm # Show LLM calls (request/response)
    python scripts/langfuse_traces.py -g <obs_id>      # Get specific observation
    python scripts/langfuse_traces.py --search karla   # Search traces by name
    python scripts/langfuse_traces.py --last 5         # Show last N traces
"""

import argparse
import ast
import json
import os
import sys
from datetime import datetime, timedelta

# Load .env from script's parent directory (karla root)
from pathlib import Path
from dotenv import load_dotenv

script_dir = Path(__file__).parent.parent
load_dotenv(script_dir / ".env")

# Langfuse config
LANGFUSE_PUBLIC_KEY = os.environ.get("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.environ.get("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3044")

if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
    print("Error: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set in .env")
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
        print(f"{'ID':<40} {'Type':<12} {'Name':<28} {'Duration':<10}")
        print("-" * 95)

        for obs in observations.data:
            obs_id = obs.id[:38] + ".." if len(obs.id) > 40 else obs.id
            obs_type = getattr(obs, 'type', 'UNKNOWN')
            obs_name = (getattr(obs, 'name', '-') or '-')[:26]
            if len(getattr(obs, 'name', '-') or '-') > 26:
                obs_name += ".."

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

            print(f"{obs_id:<40} {obs_type:<12} {obs_name:<28} {duration:<10}")

        return observations.data

    except Exception as e:
        print(f"Error fetching observations: {e}")
        return []


def get_llm_calls(trace_id: str):
    """Get LLM calls (request/response) from a trace - FULL telemetry as JSON."""
    langfuse = get_client()

    try:
        observations = langfuse.api.observations.get_many(trace_id=trace_id, limit=100)

        # Find convert_response observations - they have both request and response
        llm_obs = [
            obs for obs in observations.data
            if getattr(obs, 'name', '') == 'OpenAIClient.convert_response_to_chat_completion'
        ]

        results = []
        for obs in llm_obs:
            metadata = getattr(obs, 'metadata', {}) or {}
            attrs = metadata.get('attributes', {})

            call_data = {
                "obs_id": obs.id,
                "trace_id": trace_id,
            }

            # Parse each attribute
            for key, value in attrs.items():
                # Clean up key name
                clean_key = key.replace("parameter.", "")
                try:
                    call_data[clean_key] = ast.literal_eval(value)
                except:
                    call_data[clean_key] = value

            results.append(call_data)

        print(json.dumps(results, indent=2, default=str))
        return results

    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
        return []


def get_observation(obs_id: str):
    """Get a specific observation with full details."""
    langfuse = get_client()

    try:
        obs = langfuse.api.observations.get(obs_id)

        print(f"Observation: {obs.id}")
        print(f"Type: {getattr(obs, 'type', '-')}")
        print(f"Name: {getattr(obs, 'name', '-')}")
        print(f"Status: {getattr(obs, 'status', '-')}")
        print(f"Trace ID: {getattr(obs, 'trace_id', '-')}")

        # Timing
        start = getattr(obs, 'start_time', None)
        end = getattr(obs, 'end_time', None)
        if start:
            print(f"Start: {start}")
        if end:
            print(f"End: {end}")
        if start and end and not isinstance(start, str):
            print(f"Duration: {(end - start).total_seconds():.2f}s")

        # Model info for generations
        if hasattr(obs, 'model') and obs.model:
            print(f"Model: {obs.model}")

        # Usage
        if hasattr(obs, 'usage') and obs.usage:
            usage = obs.usage
            print(f"\nToken Usage:")
            for k, v in (usage.items() if isinstance(usage, dict) else vars(usage).items()):
                if v and not k.startswith('_'):
                    print(f"  {k}: {v}")

        # Input
        if hasattr(obs, 'input') and obs.input:
            print(f"\n{'='*60}")
            print("INPUT:")
            print(f"{'='*60}")
            import json
            if isinstance(obs.input, (dict, list)):
                print(json.dumps(obs.input, indent=2, default=str))
            else:
                print(obs.input)

        # Output
        if hasattr(obs, 'output') and obs.output:
            print(f"\n{'='*60}")
            print("OUTPUT:")
            print(f"{'='*60}")
            import json
            if isinstance(obs.output, (dict, list)):
                print(json.dumps(obs.output, indent=2, default=str))
            else:
                print(obs.output)

        # Metadata
        if hasattr(obs, 'metadata') and obs.metadata:
            print(f"\n{'='*60}")
            print("METADATA:")
            print(f"{'='*60}")
            import json
            print(json.dumps(obs.metadata, indent=2, default=str))

        return obs

    except Exception as e:
        print(f"Error fetching observation {obs_id}: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(description="Query Langfuse traces for Karla/Letta")
    parser.add_argument("trace_id", nargs="?", help="Specific trace ID to fetch")
    parser.add_argument("--search", "-s", help="Search traces by name")
    parser.add_argument("--last", "-n", type=int, default=20, help="Number of traces to show")
    parser.add_argument("--observations", "-o", action="store_true", help="Show observations for trace")
    parser.add_argument("--llm", "-l", action="store_true", help="Show LLM calls (request/response)")
    parser.add_argument("--type", "-t", help="Filter observations by type (GENERATION, SPAN, etc.)")
    parser.add_argument("--get-obs", "-g", help="Get specific observation by ID (full details)")

    args = parser.parse_args()

    # Don't print header for JSON output modes
    if not args.llm:
        print(f"Langfuse: {LANGFUSE_HOST}")
        print()

    if args.get_obs:
        get_observation(args.get_obs)
    elif args.trace_id:
        if args.llm:
            get_llm_calls(args.trace_id)
        elif args.observations:
            get_observations(args.trace_id, args.type)
        else:
            get_trace(args.trace_id)
    else:
        list_traces(limit=args.last, name_filter=args.search)


if __name__ == "__main__":
    main()
