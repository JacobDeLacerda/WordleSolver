# --- START OF FILE solver.py ---

import streamlit as st
import re
import string
from collections import Counter, defaultdict
from typing import List, Tuple, Set
import random

# --- WordleSolver Class ---
class WordleSolver:
    def __init__(self, wordlist_path: str, answers_path: str = None):
        # Store paths for potential reference/reset
        self.wordlist_path = wordlist_path
        self.answers_path = answers_path

        self.all_words = self.load_words(wordlist_path)
        if not self.all_words:
            self.likely_answers = set()
            self.possible_answers = set()
            # Error handled in get_solver which calls st.stop()
            return

        self.likely_answers = set()
        if answers_path:
            potential_answers = self.load_words(answers_path)
            if potential_answers:
                self.likely_answers = potential_answers.intersection(self.all_words)
                if not self.likely_answers:
                    st.warning(f"'{answers_path}' loaded, but had no words in common with '{wordlist_path}'. Prioritization disabled.")
            else:
                 st.warning(f"Could not load or parse '{answers_path}'. Prioritization disabled.")
        else:
            st.info("No separate answers file provided. Solver will only use the main wordlist.")
            # If no answers file, treat all words as "likely" to avoid immediate switch
            self.likely_answers = self.all_words.copy()

        self.possible_answers = self.all_words.copy()
        self.guesses_made = 0
        self.feedback_history = []
        self._known_letters = ['' for _ in range(5)]
        self._misplaced_letters = [set() for _ in range(5)]
        self._present_letters = set()
        self._excluded_letters = set()
        # --- Add state flag for suggestion strategy ---
        self.switched_to_full_list = False

    # --- load_words remains the same ---
    def load_words(self, filepath: str) -> set[str]:
        """Loads words from a file, ensuring they are valid."""
        try:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    words = {word.strip().lower() for word in f if len(word.strip()) == 5 and word.strip().isalpha()}
            except UnicodeDecodeError:
                 st.warning(f"UTF-8 decoding failed for '{filepath}', trying default encoding.")
                 with open(filepath, 'r') as f:
                    words = {word.strip().lower() for word in f if len(word.strip()) == 5 and word.strip().isalpha()}

            if not words:
                st.warning(f"Warning: No valid 5-letter words found in '{filepath}'.")
                return set()
            return words
        except FileNotFoundError:
            # Use stored paths to check if it's the main one missing
            if filepath == self.wordlist_path:
                 st.error(f"Error: Main wordlist file not found at '{filepath}'. Cannot continue.")
            else:
                 st.warning(f"Optional file not found at '{filepath}'.")
            return set()
        except Exception as e:
            st.error(f"An error occurred loading '{filepath}': {e}")
            return set()

    # --- reset_solver_state ---
    # Modified to reset the switch flag
    def reset_solver_state(self):
        """Resets the internal state derived from feedback AND the list switch flag."""
        self._known_letters = ['' for _ in range(5)]
        self._misplaced_letters = [set() for _ in range(5)]
        self._present_letters = set()
        self._excluded_letters = set()
        self.switched_to_full_list = False # Reset switch on new game

    # --- _update_internal_state_from_history remains the same ---
    def _update_internal_state_from_history(self):
        """Rebuilds internal G/Y/X tracking from feedback_history."""
        self.reset_solver_state() # Includes resetting the switch flag initially
        # ... (rest of the G/Y/X logic is identical) ...
        letter_counts_in_feedback = Counter() # Keep track of G/Y counts per letter across all guesses

        for guess, feedback in self.feedback_history:
            current_guess_letter_counts = Counter(guess)
            confirmed_non_gray_counts_in_guess = Counter() # Track non-gray instances *within this guess*

            # First pass for Greens
            for i, (letter, status) in enumerate(zip(guess, feedback)):
                if status == 'G':
                    self._known_letters[i] = letter
                    self._present_letters.add(letter)
                    confirmed_non_gray_counts_in_guess[letter] += 1
                    letter_counts_in_feedback[letter] = max(letter_counts_in_feedback[letter], confirmed_non_gray_counts_in_guess[letter])


            # Second pass for Yellows and Grays
            for i, (letter, status) in enumerate(zip(guess, feedback)):
                if status == 'Y':
                    self._misplaced_letters[i].add(letter)
                    self._present_letters.add(letter)
                    confirmed_non_gray_counts_in_guess[letter] += 1
                    letter_counts_in_feedback[letter] = max(letter_counts_in_feedback[letter], confirmed_non_gray_counts_in_guess[letter])

                elif status == 'X':
                     # Simplified Exclusion: Exclude if in _excluded_letters AND not green/yellow anywhere
                    if letter not in self._present_letters and all(gl != letter for gl in self._known_letters):
                         self._excluded_letters.add(letter)


    # --- calculate_positional_frequencies remains the same ---
    def calculate_positional_frequencies(self, words: set[str]) -> list[Counter]:
        """Calculates letter frequencies for each position."""
        positional_frequencies = [Counter() for _ in range(5)]
        if not words: return positional_frequencies
        for word in words:
            for i, letter in enumerate(word):
                positional_frequencies[i][letter] += 1
        return positional_frequencies

    # --- calculate_letter_frequencies remains the same ---
    def calculate_letter_frequencies(self, words: set[str]) -> Counter:
        """Calculates overall letter frequencies."""
        if not words: return Counter()
        return Counter("".join(words))

    # --- score_word remains mostly the same (bonus logic less critical now but kept for tie-breaking) ---
    def score_word(self, word: str, positional_frequencies: list[Counter], letter_frequencies: Counter, current_possible_words: set[str], elimination_mode: bool = False) -> float:
        """Scores a word based on frequencies and elimination potential."""
        score = 0.0
        used_letters = set()

        is_currently_possible = word in current_possible_words
        is_likely_answer = word in self.likely_answers # Check against original likely set

        # --- Penalties ---
        for i, letter in enumerate(word):
            if letter in self._excluded_letters:
                 if letter not in self._present_letters and letter not in self._known_letters:
                    score -= 1000
            if letter in self._misplaced_letters[i]:
                 score -= 50
            if self._known_letters[i] and self._known_letters[i] != letter:
                 score -= 200

        # --- Scoring based on letter value ---
        for i, letter in enumerate(word):
            if letter not in used_letters:
                score += positional_frequencies[i].get(letter, 0)
                if elimination_mode:
                    # Frequencies based on *all* current possible words provide better info
                    score += letter_frequencies.get(letter, 0) * 0.6
                used_letters.add(letter)

        # --- Bonuses (Mainly for tie-breaking within the chosen pool) ---
        if is_likely_answer and is_currently_possible and not elimination_mode:
             score *= 1.8 # Still useful if scoring within likely pool
        elif is_currently_possible and not elimination_mode:
             score *= 1.1

        duplicate_penalty_factor = 0.95 if is_likely_answer else 0.85
        if len(set(word)) < 5:
             score *= duplicate_penalty_factor

        return max(score, -500)

    # --- filter_words remains the same ---
    # It correctly filters self.possible_answers based on ALL rules.
    # The suggestion logic will decide which subset of these to use.
    def filter_words(self) -> set[str]:
        """Filters the possible words (which starts as ALL words) based on accumulated feedback."""
        self._update_internal_state_from_history() # Updates G/Y/X state
        filtered = self.all_words.copy() # Start fresh filter from all words each time

        # Apply known green letters
        for i, known_letter in enumerate(self._known_letters):
            if known_letter:
                filtered = {word for word in filtered if len(word) > i and word[i] == known_letter}

        # Apply known present (yellow) letters and their misplaced positions
        for letter in self._present_letters:
             filtered = {word for word in filtered if letter in word}
        for i, misplaced_set in enumerate(self._misplaced_letters):
            for letter in misplaced_set:
                 filtered = {word for word in filtered if len(word) > i and word[i] != letter}

        # Apply fully excluded (gray) letters
        active_exclusions = {l for l in self._excluded_letters if l not in self._present_letters and all(gl != l for gl in self._known_letters)}
        for letter in active_exclusions:
             filtered = {word for word in filtered if letter not in word}

        # Handle duplicate letter counts implied by feedback
        min_letter_counts = Counter()
        exact_letter_counts = {}

        for guess, feedback in self.feedback_history:
             guess_counts = Counter(guess)
             non_gray_count_in_guess = Counter()
             gray_count_in_guess = Counter()
             for i, (letter, status) in enumerate(zip(guess, feedback)):
                 if status in ('G', 'Y'): non_gray_count_in_guess[letter] += 1
                 elif status == 'X': gray_count_in_guess[letter] += 1

             for letter, count_in_guess in guess_counts.items():
                 min_letter_counts[letter] = max(min_letter_counts[letter], non_gray_count_in_guess[letter])
                 if gray_count_in_guess[letter] > 0:
                      exact_letter_counts[letter] = non_gray_count_in_guess[letter]

        # Apply min/exact count filtering
        final_filtered = set()
        for word in filtered:
            word_counts = Counter(word)
            valid = True
            for letter, min_count in min_letter_counts.items():
                if word_counts[letter] < min_count: valid = False; break
            if not valid: continue
            for letter, exact_count in exact_letter_counts.items():
                 if word_counts[letter] != exact_count: valid = False; break
            if valid: final_filtered.add(word)

        # Update the solver's primary list of possible answers
        self.possible_answers = final_filtered
        return self.possible_answers


    # --- *** COMPLETELY REVISED suggest_guess *** ---
    def suggest_guess(self) -> str:
        """
        Suggests the best guess according to the two-phase strategy:
        1. Prioritize words from the original 'likely_answers' list that fit the feedback.
        2. If no likely answers fit, switch to suggesting from all remaining possible words.
        """
        # 1. Filter possibilities based on latest feedback
        current_possible = self.filter_words() # Updates self.possible_answers

        # 2. Handle edge case: No words fit the feedback
        if not current_possible:
            return "No valid words remaining."

        # 3. Check the intersection: Possible words that were in the original answers.txt
        possible_and_likely = current_possible.intersection(self.likely_answers)

        # 4. Determine which pool of words to suggest from
        pool_to_suggest_from = set()
        phase_message = "" # For debugging or UI hint

        if not self.switched_to_full_list and possible_and_likely:
            # --- Phase 1: Still likely answers available ---
            pool_to_suggest_from = possible_and_likely
            phase_message = "(Suggesting from Likely Answers)"
            # print(f"Phase 1: Suggesting from {len(pool_to_suggest_from)} likely words.") # Debug
        else:
            # --- Phase 2: No likely answers left, OR already switched ---
            if not self.switched_to_full_list:
                # This is the moment of switching
                self.switched_to_full_list = True
                st.toast("Switching: No likely answers match feedback. Considering all valid words now.") # Notify user
                # print("Phase Switch: No likely answers remain.") # Debug

            pool_to_suggest_from = current_possible # Use all remaining possibilities
            phase_message = "(Suggesting from All Possible Words)"
            # print(f"Phase 2: Suggesting from {len(pool_to_suggest_from)} remaining possible words.") # Debug

            # If the pool is somehow empty after the switch (shouldn't happen if current_possible wasn't empty)
            if not pool_to_suggest_from:
                 return "Error: Pool became empty after switch."


        # 5. Determine if elimination mode should be used for the *selected pool*
        # Use elimination if few guesses made OR pool is large, encouraging info gain
        elimination_mode = (st.session_state.guesses_made < 2 and len(pool_to_suggest_from) > 1) or \
                           (len(pool_to_suggest_from) > 50 and st.session_state.guesses_made < 4)

        # 6. Calculate frequencies based on ALL current possible words (for best info)
        #    We use this broader frequency info even when scoring a smaller pool.
        overall_pos_freq = self.calculate_positional_frequencies(current_possible)
        overall_letter_freq = self.calculate_letter_frequencies(current_possible)

        # 7. Score words *only within the selected pool*
        best_word = ""
        best_score = -float('inf')

        # Decide if we need to score *outside* the suggestion pool for elimination
        # If in elimination mode AND Phase 1, we *might* score words from all_words
        # that *aren't* in possible_and_likely to find a better eliminator.
        # Let's try a simpler approach first: Only score within the suggestion pool.
        word_pool_to_score = pool_to_suggest_from

        # --- Refined Elimination Logic (Optional but potentially better): ---
        # If elimination_mode is True, maybe we should *always* score from `self.all_words`
        # that haven't been guessed, but use the `score_word` bonus/penalty logic
        # to heavily favor words within `pool_to_suggest_from`?
        # Let's stick to the stricter phase logic for now as requested.

        # print(f"Scoring Pool Size: {len(word_pool_to_score)}, Elim Mode: {elimination_mode}") # Debug

        for word in word_pool_to_score:
            # Don't suggest words already guessed
            if any(word == hist[0] for hist in self.feedback_history):
                continue

            # Score using overall frequencies but applying to the word from the chosen pool
            score = self.score_word(word, overall_pos_freq, overall_letter_freq, current_possible, elimination_mode)

            # Tie-breaking (simplified as pool is already pre-filtered)
            # Prefer words with more unique letters in ties? Or just alphabetical?
            if score > best_score:
                 best_score = score
                 best_word = word
            elif score == best_score:
                 # Alphabetical tie-break for consistency
                 if word < best_word:
                      best_word = word

        # Handle case where scoring yields no best word (e.g., all penalized heavily)
        if not best_word and pool_to_suggest_from:
             # Fallback: return the alphabetically first word in the suggestion pool
             return sorted(list(pool_to_suggest_from))[0]
        elif not best_word:
             return "Could not determine guess." # Should be rare

        # print(f"Suggesting: {best_word} {phase_message}") # Debug
        return best_word


# --- Streamlit App ---

# Constants (remain the same)
MAX_GUESSES = 6
WORD_LENGTH = 5
CORRECT = "G"
PRESENT = "Y"
ABSENT = "X"
DEFAULT_FEEDBACK = [ABSENT] * WORD_LENGTH
FEEDBACK_OPTIONS = [ABSENT, PRESENT, CORRECT]
COLORS = {CORRECT: "#6aaa64", PRESENT: "#c9b458", ABSENT: "#787c7e", "empty": "#ffffff", "tbd": "#d3d6da"}

# Helper Functions (remain the same)
@st.cache_resource
def get_solver():
    wordlist_file = "wordlist.txt"
    answers_file = "answers.txt" # Or None
    _solver = WordleSolver(wordlist_file, answers_file)
    if not _solver.all_words:
        st.error("Failed to load the main wordlist. Please check the file and path.")
        st.stop()
    return _solver

def get_color(status, is_feedback_button=False):
    if is_feedback_button and status == ABSENT:
        return COLORS.get("tbd", COLORS["empty"])
    return COLORS.get(status, COLORS["empty"])

def display_guess_grid(history):
    st.markdown("""<style>...</style>""", unsafe_allow_html=True) # CSS same as before
    # Display past guesses
    for guess_word, feedback_list in history:
        cols = st.columns(WORD_LENGTH)
        for i, letter in enumerate(guess_word):
            state = feedback_list[i] if i < len(feedback_list) else "empty"
            letter_display = letter if i < len(guess_word) else " "
            with cols[i]:
                st.markdown(f'<div class="tile" data-state="{state}">{letter_display}</div>', unsafe_allow_html=True)
    # Display empty rows
    remaining_guesses = MAX_GUESSES - len(history)
    for _ in range(remaining_guesses):
        cols = st.columns(WORD_LENGTH)
        for i in range(WORD_LENGTH):
            with cols[i]:
                st.markdown(f'<div class="tile" data-state="empty"> </div>', unsafe_allow_html=True)


# --- App Initialization & State (remain the same) ---
st.set_page_config(page_title="Wordle Solver+", layout="wide")
st.title("🧠 Wordle Solver+")
st.caption("Enter guess, click squares for feedback (Gray->Yellow->Green), Submit.")

solver = get_solver()

# Initialize session state (remains the same)
if 'solver_history' not in st.session_state:
    st.session_state.solver_history = []
    st.session_state.display_history = []
    st.session_state.guesses_made = 0
    st.session_state.current_feedback = list(DEFAULT_FEEDBACK)
    st.session_state.game_over = False
    st.session_state.solved = False
    st.session_state.last_suggested = ""
    st.session_state.current_guess_input = ""


# --- New Game Button ---
# Needs to reset the solver's switch flag too
if st.sidebar.button("🔄 New Game"):
    st.session_state.solver_history = []
    st.session_state.display_history = []
    st.session_state.guesses_made = 0
    st.session_state.current_feedback = list(DEFAULT_FEEDBACK)
    st.session_state.game_over = False
    st.session_state.solved = False
    st.session_state.last_suggested = ""
    st.session_state.current_guess_input = ""

    # Reset solver's internal state tracking, possibilities, AND the switch flag
    solver.feedback_history = []
    solver.possible_answers = solver.all_words.copy()
    solver.reset_solver_state() # This now resets the switch flag too

    st.rerun()


# --- Main Game Area ---
grid_col, control_col = st.columns([2, 1])

with grid_col:
    st.subheader("Guess Grid")
    display_guess_grid(st.session_state.display_history)

with control_col:
    st.subheader("Controls")

    if st.session_state.game_over:
        # Game over logic (remains the same)
        if st.session_state.solved:
            st.success(f"Solved in {st.session_state.guesses_made} guesses! 🎉")
        else:
            st.error("Game Over! Failed to solve within 6 guesses.")
        final_possibilities = solver.possible_answers
        if len(final_possibilities) == 1:
             st.info(f"The answer was likely: **{list(final_possibilities)[0].upper()}**")
        elif 1 < len(final_possibilities) <= 10:
             st.info(f"Possible remaining answers: {', '.join(sorted([w.upper() for w in final_possibilities]))}")
        elif len(final_possibilities) > 10:
             st.info(f"{len(final_possibilities)} possibilities remained.")
        else:
             st.warning("No possible words match the feedback provided.")
        st.write("Start a 'New Game' from the sidebar.")

    else:
        # --- Solver Suggestion ---
        # Note: suggest_guess() now embodies the phase logic
        suggested_guess = solver.suggest_guess() # No elim_mode param needed here directly
        st.session_state.last_suggested = suggested_guess

        # Display remaining count using the solver's current state
        remaining_count = len(solver.possible_answers)
        st.metric("Possible Words Remaining", remaining_count)

        # Add suffix indicating suggestion source based on the switch flag
        suggestion_suffix = ""
        if solver.switched_to_full_list:
             suggestion_suffix = " (From Full List)"
        elif suggested_guess in solver.likely_answers:
              suggestion_suffix = " (From Likely List)"
        # Add more detail? (e.g., elimination hint?) - Keep simple for now

        st.info(f"Solver Suggests: **{suggested_guess.upper()}**{suggestion_suffix}")

        # --- User Guess Input (remains the same) ---
        guess_placeholder = suggested_guess.upper()
        guess = st.text_input(
            "Enter Your Guess:", placeholder=guess_placeholder, max_chars=WORD_LENGTH,
            key="user_guess_input_field", value=st.session_state.get("current_guess_input", "")
        ).lower().strip()
        st.session_state.current_guess_input = guess

        # --- Feedback Input (remains the same) ---
        st.write("Set feedback for your guess:")
        if len(guess) == WORD_LENGTH and guess.isalpha():
            feedback_cols = st.columns(WORD_LENGTH)
            current_feedback_list = st.session_state.current_feedback
            for i, letter in enumerate(guess):
                with feedback_cols[i]:
                    current_status = current_feedback_list[i]
                    tile_color = get_color(current_status)
                    border_color = tile_color if current_status != ABSENT else "#878a8c"
                    text_color = "white" if current_status != ABSENT else "black"
                    button_html = f"""<div style="display: flex; ..."> {letter.upper()} </div>""" # Same HTML as before
                    if st.button(f"##{letter.upper()}_{i}", key=f"fb_btn_{i}", help="Click to cycle: Gray -> Yellow -> Green"):
                         current_index = FEEDBACK_OPTIONS.index(current_status)
                         next_index = (current_index + 1) % len(FEEDBACK_OPTIONS)
                         st.session_state.current_feedback[i] = FEEDBACK_OPTIONS[next_index]
                         st.rerun()
                    st.markdown(button_html, unsafe_allow_html=True)

            # --- Submit Button (remains the same) ---
            st.write("---")
            if st.button("✅ Submit Guess and Feedback", use_container_width=True):
                if len(guess) != WORD_LENGTH or not guess.isalpha(): st.warning("Enter valid 5-letter word.")
                elif guess not in solver.all_words: st.warning(f"'{guess.upper()}' not in valid word list.")
                else:
                    feedback_str = "".join(st.session_state.current_feedback)
                    # Update Solver History (filtering happens in suggest_guess)
                    solver.feedback_history.append((guess, feedback_str))
                    # Update Streamlit State
                    st.session_state.display_history.append((guess, list(st.session_state.current_feedback)))
                    st.session_state.guesses_made += 1
                    # Check win/loss
                    if feedback_str == CORRECT * WORD_LENGTH: st.session_state.solved = True; st.session_state.game_over = True
                    elif st.session_state.guesses_made >= MAX_GUESSES: st.session_state.game_over = True
                    # Reset for next guess input
                    st.session_state.current_feedback = list(DEFAULT_FEEDBACK)
                    st.session_state.current_guess_input = ""
                    # Rerun to get next suggestion
                    st.rerun()
        elif guess: st.warning("Type 5-letter word.")
        else: st.caption("Type guess above.")

# Optional: Display remaining words (remain the same logic)
if not st.session_state.game_over and solver.possible_answers and 0 < len(solver.possible_answers) <= 20 :
    with grid_col:
        st.write("---"); st.write(f"**Top Potential Answers ({len(solver.possible_answers)} total):**")
        likely = sorted([w for w in solver.possible_answers if w in solver.likely_answers])
        other = sorted([w for w in solver.possible_answers if w not in solver.likely_answers])
        display = likely + other
        st.info(", ".join(display[:20]))
elif st.session_state.game_over and solver.possible_answers and len(solver.possible_answers) > 1 and len(solver.possible_answers) <=20:
     with grid_col:
        st.write("---"); st.write(f"**Final Potential Answers ({len(solver.possible_answers)}):**")
        likely = sorted([w for w in solver.possible_answers if w in solver.likely_answers])
        other = sorted([w for w in solver.possible_answers if w not in solver.likely_answers])
        display = likely + other
        st.info(", ".join(display[:20]))

# --- END OF FILE solver.py ---
