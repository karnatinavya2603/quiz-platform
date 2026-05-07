import sys
import subprocess


def run_code(code, inp=""):
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            input=inp, text=True, capture_output=True, timeout=5
        )
        return result.stdout.strip() if result.stdout else result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "Error: Time limit exceeded"
    except Exception as e:
        return f"Error: {e}"


def generate_testcases(question):
    q = question.lower()
    if "reverse" in q:
        return [("hello", "olleh"), ("world", "dlrow"), ("python", "nohtyp")]
    elif "largest" in q or "maximum" in q or "max" in q:
        return [("1 2 3", "3"), ("10 5 8", "10"), ("7 9 2", "9")]
    elif "sum" in q:
        return [("1 2 3", "6"), ("10 20", "30"), ("5 5 5", "15")]
    elif "vowel" in q:
        return [("hello", "2"), ("aeiou", "5"), ("python", "1")]
    elif "factorial" in q:
        return [("5", "120"), ("3", "6"), ("1", "1")]
    elif "fibonacci" in q:
        return [("5", "0 1 1 2 3")]
    elif "even" in q or "odd" in q:
        return [("4", "Even"), ("7", "Odd")]
    elif "palindrome" in q:
        return [("racecar", "Yes"), ("hello", "No")]
    elif "sort" in q:
        return [("3 1 2", "1 2 3"), ("5 4 3", "3 4 5")]
    return [("1", "1")]
