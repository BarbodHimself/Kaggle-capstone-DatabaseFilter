import pytest
from app.agent import app

def test_clean_query_optimization():
    """
    Test that a clean SELECT query successfully routes through sanitization,
    gets passed to the optimization node, and outputs a SUCCESS execution status.
    """
    initial_state = {
        "raw_query": "SELECT * FROM users WHERE active = 1",
        "sanitized_query": None,
        "optimized_query": None,
        "query_history": [],
        "session_logs": [],
        "current_errors": [],
        "execution_status": "INITIALIZED"
    }
    
    response = app.invoke(initial_state)
    
    # Assertions
    assert response["execution_status"] == "SUCCESS", "The clean query should route to SUCCESS."
    assert response["sanitized_query"] is not None, "Sanitized query must be populated."
    assert "SELECT" in response["sanitized_query"].upper()
    assert response["optimized_query"] is not None, "Optimized query should be returned by the model."
    assert len(response["current_errors"]) == 0, "There should be no errors caught for a clean query."

def test_malicious_injection_payload():
    """
    Test that a malicious multi-statement payload with a destructive keyword (DROP)
    is caught by the sanitization node and immediately routes to a SANITIZATION_FAILED state.
    """
    initial_state = {
        "raw_query": "SELECT * FROM metrics; DROP TABLE users;",
        "sanitized_query": None,
        "optimized_query": None,
        "query_history": [],
        "session_logs": [],
        "current_errors": [],
        "execution_status": "INITIALIZED"
    }
    
    response = app.invoke(initial_state)
    
    # Assertions
    assert response["execution_status"] == "SANITIZATION_FAILED", "The graph should fail at sanitization."
    assert response["optimized_query"] is None, "Optimization must NOT run for a malicious payload."
    assert len(response["current_errors"]) > 0, "Errors should be logged for malicious payloads."
    
    error_messages = str(response["current_errors"])
    assert "DROP" in error_messages, "The destructive keyword DROP should be flagged."
    assert "Multi-statement" in error_messages, "Multi-statement injection attempt should be flagged."
