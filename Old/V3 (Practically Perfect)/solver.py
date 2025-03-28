import streamlit as st
import re
import string
from collections import Counter, defaultdict
from typing import List, Tuple, Set

# --- Paste or Import the WordleSolver Class ---
# (Identical to the previous version, included here for completeness)
class WordleSolver:
    def __init__(self, wordlist_path: str, answers_path: str = None):
        self.all_words = self.load_words(wordlist_path)
        # Use answers_path if provided, otherwise use all_words
        if answers_path:
            potential_answers = self.load_words(answers_path)
            # Ensure answers are also in the main word list
            self.possible_answers = potential_answers.intersection(self.all_words)
            if not self.possible_answers:
                st.warning("Answers file resulted in empty set after intersection with wordlist. Using full wordlist for answers.")
                self.possible_answers = self.all_words.copy()
        else:
            self.possible_answers = self.all_words.copy()

        self.guesses_made = 0
        self.feedback_history = []  # Store (guess, feedback) tuples
        # --- State tracking specific to filtering logic ---
        self._known_letters = ['' for _ in range(5)]  # Green letters ('G')
        self._misplaced_letters = [set() for _ in range(5)] # Yellow letters ('Y'), per position they *cannot* be
        self._present_letters = set() # All yellow letters found anywhere
        self._excluded_letters = set() # Gray letters ('X')

    def load_words(self, filepath: str) -> set[str]:
        """Loads words from a file, ensuring they are valid."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f: # Added encoding
                words = {word.strip().lower() for word in f if len(word.strip()) == 5 and word.strip().isalpha()}
            if not words:
                st.error(f"Error: No valid 5-letter words found in '{filepath}'. Please check the file.")
                return set()
            return words
        except FileNotFoundError:
            st.error(f"Error: File not found at '{filepath}'. Please ensure it's in the same directory as the script.")
            return set()
        except Exception as e:
            st.error(f"An error occurred loading '{filepath}': {e}")
            return set()

    def reset_solver_state(self):
        """Resets the internal state derived from feedback."""
        self._known_letters = ['' for _ in range(5)]
        self._misplaced_letters = [set() for _ in range(5)]
        self._present_letters = set()
        self._excluded_letters = set()

    def _update_internal_state_from_history(self):
        """Rebuilds internal G/Y/X tracking from feedback_history."""
        self.reset_solver_state()
        letter_counts_in_feedback = Counter()

        for guess, feedback in self.feedback_history:
            current_guess_letter_counts = Counter(guess)
            confirmed_non_gray_counts = Counter() # Track how many non-gray instances of each letter we've seen *in this guess*

            # First pass for Greens
            for i, (letter, status) in enumerate(zip(guess, feedback)):
                 if status == 'G':
                    self._known_letters[i] = letter
                    self._present_letters.add(letter)
                    confirmed_non_gray_counts[letter] += 1

            # Second pass for Yellows and Grays
            for i, (letter, status) in enumerate(zip(guess, feedback)):
                if status == 'Y':
                    self._misplaced_letters[i].add(letter)
                    self._present_letters.add(letter)
                    confirmed_non_gray_counts[letter] += 1
                elif status == 'X':
                    # Exclude 'X' letter ONLY if its count doesn't exceed the confirmed non-gray count
                    # This handles cases like guess 'BOOOK' with feedback 'XGXXG' for answer 'BROOM'
                    # The first 'O' is gray, but the second is green. 'O' should not be fully excluded.
                    if confirmed_non_gray_counts[letter] < current_guess_letter_counts[letter]:
                        # Only add to excluded if it's not known green/yellow elsewhere
                         if letter not in self._present_letters and letter not in self._known_letters:
                            self._excluded_letters.add(letter)


    def calculate_positional_frequencies(self, words: set[str]) -> list[Counter]:
        """Calculates letter frequencies for each position."""
        positional_frequencies = [Counter() for _ in range(5)]
        for word in words:
            for i, letter in enumerate(word):
                positional_frequencies[i][letter] += 1
        return positional_frequencies

    def calculate_letter_frequencies(self, words: set[str]) -> Counter:
        """Calculates overall letter frequencies."""
        return Counter("".join(words))

    def score_word(self, word: str, positional_frequencies: list[Counter], letter_frequencies: Counter, possible_answers: set[str], elimination_mode: bool = False) -> float:
        """Scores a word based on frequencies and elimination potential."""
        score = 0.0
        used_letters = set()

        is_possible_answer = word in possible_answers

        for i, letter in enumerate(word):
            # Heavily penalize guessing letters already known to be excluded
            if letter in self._excluded_letters:
                score -= 1000 # Strong penalty
                continue # Don't reward excluded letters

            # Penalize guessing letters known to be misplaced in this specific position
            if letter in self._misplaced_letters[i]:
                 score -= 50 # Moderate penalty

            # Penalize using green letters in wrong positions
            if self._known_letters[i] and self._known_letters[i] != letter:
                 pass # Already handled by filtering, but could add penalty if needed
            elif any(self._known_letters[pos] == letter for pos in range(5) if pos != i):
                 pass # Already handled by filtering


            if letter not in used_letters:
                # Core scoring based on frequency in remaining *possible answers*
                score += positional_frequencies[i][letter] # Positional value

                # Elimination bonus: Add score based on overall frequency in remaining words
                # to incentivize revealing new information, especially in elimination mode.
                if elimination_mode:
                    score += letter_frequencies.get(letter, 0) * 0.5 # Weighted elimination bonus

                used_letters.add(letter)

        # Bonus for words that *could* be the answer - prioritize them slightly unless in pure elimination
        if is_possible_answer and not elimination_mode:
            score *= 1.2

        # Penalize words with duplicate letters slightly, unless they are highly frequent
        if len(set(word)) < 5:
             score *= 0.9

        return score


    def filter_words(self) -> set[str]:
        """Filters the possible words based on accumulated feedback."""
        self._update_internal_state_from_history() # Ensure internal state matches history
        filtered = self.possible_answers.copy()

        # Apply known green letters
        for i, known_letter in enumerate(self._known_letters):
            if known_letter:
                filtered = {word for word in filtered if word[i] == known_letter}

        # Apply known present (yellow) letters and their misplaced positions
        for letter in self._present_letters:
             # Ensure the letter is present
             filtered = {word for word in filtered if letter in word}
        for i, misplaced_set in enumerate(self._misplaced_letters):
            for letter in misplaced_set:
                filtered = {word for word in filtered if word[i] != letter} # Cannot be in this spot

        # Apply excluded (gray) letters
        # Crucially, only exclude if not present as Green or Yellow
        active_exclusions = self._excluded_letters - self._present_letters - set(filter(None, self._known_letters))
        for letter in active_exclusions:
             filtered = {word for word in filtered if letter not in word}

        # Handle duplicate letter counts implied by feedback (Advanced)
        min_letter_counts = Counter()
        max_letter_counts = defaultdict(lambda: 5) # Max 5 unless proven otherwise

        for guess, feedback in self.feedback_history:
             guess_counts = Counter(guess)
             non_gray_counts = Counter()
             for i, (letter, status) in enumerate(zip(guess, feedback)):
                 if status in ('G', 'Y'):
                     non_gray_counts[letter] += 1

             for letter, count in guess_counts.items():
                 # Minimum count required is the number of G/Y occurrences
                 min_letter_counts[letter] = max(min_letter_counts[letter], non_gray_counts[letter])

                 # If a letter had gray feedback, AND the non-gray count equals the minimum required count seen so far,
                 # then we know the word contains *exactly* that many instances of the letter.
                 if non_gray_counts[letter] < count and letter in self._excluded_letters:
                      max_letter_counts[letter] = min(max_letter_counts[letter], non_gray_counts[letter])


        # Apply min/max count filtering
        temp_filtered = set()
        for word in filtered:
            word_counts = Counter(word)
            valid = True
            # Check minimum counts
            for letter, min_count in min_letter_counts.items():
                if word_counts[letter] < min_count:
                    valid = False
                    break
            if not valid: continue

            # Check maximum counts
            for letter, max_count in max_letter_counts.items():
                 if letter in word_counts and word_counts[letter] > max_count:
                     valid = False
                     break
            if valid:
                temp_filtered.add(word)

        self.possible_answers = temp_filtered # Update the master list
        return self.possible_answers


    def suggest_guess(self, elimination_mode: bool = False) -> str:
        """Suggests the best guess based on scoring."""
        current_possible = self.filter_words() # Ensure filtering happens first
        if not current_possible:
            return "No valid words remaining."
        if len(current_possible) == 1:
            return list(current_possible)[0] # The only possibility is the answer

        positional_frequencies = self.calculate_positional_frequencies(current_possible)
        letter_frequencies = self.calculate_letter_frequencies(current_possible)

        best_word = ""
        best_score = -float('inf') # Initialize with very low score

        # Decide which set of words to score: all words for elimination, or just possible answers
        word_pool = self.all_words if elimination_mode else current_possible

        # Optimization: If pool is huge, consider sampling or prioritizing possible answers first
        # if elimination_mode and len(word_pool) > 5000:
        #     word_pool = current_possible.union(random.sample(list(self.all_words - current_possible), 2000))


        for word in word_pool:
            # Don't suggest words already guessed
            if any(word == hist[0] for hist in self.feedback_history):
                continue

            score = self.score_word(word, positional_frequencies, letter_frequencies, current_possible, elimination_mode)

            # Tie-breaking: prefer possible answers, then alphabetical
            current_best_is_possible = best_word in current_possible
            word_is_possible = word in current_possible

            if score > best_score:
                best_score = score
                best_word = word
            elif score == best_score:
                 # Prioritize possible answers in case of score tie
                if word_is_possible and not current_best_is_possible:
                    best_word = word
                # If both or neither are possible, use alphabetical for consistency
                elif word_is_possible == current_best_is_possible and word < best_word:
                     best_word = word


        return best_word if best_word else "Could not determine best guess."


# --- Streamlit App ---

# Constants
MAX_GUESSES = 6
WORD_LENGTH = 5
CORRECT = "G"
PRESENT = "Y"
ABSENT = "X"
DEFAULT_FEEDBACK = [ABSENT] * WORD_LENGTH
FEEDBACK_OPTIONS = [ABSENT, PRESENT, CORRECT]
COLORS = {CORRECT: "#6aaa64", PRESENT: "#c9b458", ABSENT: "#787c7e", "empty": "#d3d6da"}

# Helper Functions
@st.cache_resource # Cache the solver instance loading
def get_solver():
    # --- IMPORTANT: Adjust file paths if needed ---
    wordlist_file = "wordlist.txt"
    answers_file = "answers.txt" # Make this None if you don't have it
    # --------------------------------------------
    solver = WordleSolver(wordlist_file, answers_file)
    if not solver.all_words: # Check if loading failed
        st.stop() # Stop execution if files aren't loaded
    return solver

def get_color(status):
    return COLORS.get(status, COLORS["empty"])

def display_guess_grid(history):
    st.markdown("""
        <style>
            .tile {
                display: inline-flex;
                justify-content: center;
                align-items: center;
                width: 50px;
                height: 50px;
                border: 2px solid #d3d6da;
                margin: 2px;
                font-size: 2em;
                font-weight: bold;
                text-transform: uppercase;
                color: white; /* Letter color */
            }
            .tile[data-state="G"] { background-color: #6aaa64; border-color: #6aaa64; }
            .tile[data-state="Y"] { background-color: #c9b458; border-color: #c9b458; }
            .tile[data-state="X"] { background-color: #787c7e; border-color: #787c7e; }
            .tile[data-state="empty"] { background-color: white; border-color: #d3d6da; }
            .tile[data-state="tbd"] { background-color: white; border-color: #878a8c; color: black !important; } /* Style for current guess input */
        </style>
    """, unsafe_allow_html=True)

    # Display past guesses
    for guess_word, feedback_list in history:
        cols = st.columns(WORD_LENGTH)
        for i, letter in enumerate(guess_word):
            state = feedback_list[i]
            with cols[i]:
                st.markdown(f'<div class="tile" data-state="{state}">{letter}</div>', unsafe_allow_html=True)

    # Display empty rows for remaining guesses
    remaining_guesses = MAX_GUESSES - len(history)
    for _ in range(remaining_guesses):
        cols = st.columns(WORD_LENGTH)
        for i in range(WORD_LENGTH):
            with cols[i]:
                st.markdown(f'<div class="tile" data-state="empty"> </div>', unsafe_allow_html=True)


# --- App Initialization & State ---
st.set_page_config(page_title="Streamlit Wordle Solver", layout="wide")
st.title("🧠 Streamlit Wordle Solver")
st.caption("Enter your guess, click the buttons below to set Wordle's feedback (Gray/Yellow/Green), then Submit.")

solver = get_solver()

# Initialize session state variables if they don't exist
if 'solver_history' not in st.session_state:
    st.session_state.solver_history = [] # List of (guess, feedback) tuples for the solver
    st.session_state.display_history = [] # List of (guess, feedback) for display grid
    st.session_state.guesses_made = 0
    st.session_state.current_feedback = list(DEFAULT_FEEDBACK) # Feedback for the *next* guess
    st.session_state.game_over = False
    st.session_state.solved = False
    st.session_state.last_suggested = ""
    st.session_state.current_guess_input = ""


# --- Corrected Code for "New Game" Button ---
if st.sidebar.button("New Game"):
    st.session_state.solver_history = []
    st.session_state.display_history = []
    st.session_state.guesses_made = 0
    st.session_state.current_feedback = list(DEFAULT_FEEDBACK)
    st.session_state.game_over = False
    st.session_state.solved = False
    st.session_state.last_suggested = ""
    st.session_state.current_guess_input = ""

    # Reset solver's internal state tracking
    solver.feedback_history = []

    # --- Corrected Resetting of possible_answers ---
    answers_file = "answers.txt" # Or however you define the path
    # Attempt to load the dedicated answers file
    potential_answers = solver.load_words(answers_file)

    if potential_answers:
        # If answers loaded successfully, intersect with all words
        solver.possible_answers = potential_answers.intersection(solver.all_words)
        # Handle case where intersection is empty (e.g., bad answers file)
        if not solver.possible_answers:
            st.warning(f"'{answers_file}' loaded but had no common words with the main wordlist. Using full wordlist for answers.")
            solver.possible_answers = solver.all_words.copy()
    else:
        # If answers file failed to load or was empty, fall back to using all words
        st.warning(f"Could not load '{answers_file}' or it was empty. Using full wordlist for potential answers.")
        solver.possible_answers = solver.all_words.copy()
    # --- End of Corrected Reset ---

    st.rerun() # Rerun to reflect the reset state


# --- Main Game Area ---
grid_col, control_col = st.columns([2, 1])

with grid_col:
    st.subheader("Guess Grid")
    display_guess_grid(st.session_state.display_history)

with control_col:
    st.subheader("Controls")

    if st.session_state.game_over:
        if st.session_state.solved:
            st.success(f"Solved in {st.session_state.guesses_made} guesses! 🎉")
        else:
            st.error("Game Over! Failed to solve within 6 guesses.")
        st.info(f"The word might have been: {list(solver.possible_answers)[0] if len(solver.possible_answers) == 1 else 'Could not determine'}")
        st.write("Start a 'New Game' from the sidebar.")

    else:
        # --- Solver Suggestion ---
        remaining_count = len(solver.possible_answers)
        st.write(f"Possible words remaining: **{remaining_count}**")

        # Determine if elimination mode should be used (e.g., first 2 turns or many words left)
        elimination_mode = st.session_state.guesses_made < 2 and remaining_count > 20 # Example heuristic

        suggested_guess = solver.suggest_guess(elimination_mode=elimination_mode)
        st.session_state.last_suggested = suggested_guess
        st.info(f"Solver Suggests: **{suggested_guess.upper()}** {'(Elimination Mode)' if elimination_mode and suggested_guess not in solver.possible_answers else ''}")


        # --- User Guess Input ---
        # Use the suggested guess as the default, allow user override
        if not st.session_state.current_guess_input: # Only set default if input is empty
             st.session_state.current_guess_input = suggested_guess

        guess = st.text_input(
            "Enter Your Guess:",
            value=st.session_state.current_guess_input,
            max_chars=WORD_LENGTH,
            key="user_guess_input_key" # Assign a key to help manage state
        ).lower().strip()
        st.session_state.current_guess_input = guess # Keep state updated


        # --- Feedback Input ---
        st.write("Click to set feedback for your guess:")
        if len(guess) == WORD_LENGTH and guess.isalpha():
            feedback_cols = st.columns(WORD_LENGTH)
            current_feedback_list = st.session_state.current_feedback

            for i, letter in enumerate(guess):
                with feedback_cols[i]:
                    current_status = current_feedback_list[i]
                    button_label = f"{letter.upper()}" # Show letter on button

                    # Cycle through feedback options on click
                    if st.button(button_label, key=f"fb_{i}", help=f"Click to cycle feedback for '{letter.upper()}' (Current: {current_status})"):
                        current_index = FEEDBACK_OPTIONS.index(current_status)
                        next_index = (current_index + 1) % len(FEEDBACK_OPTIONS)
                        st.session_state.current_feedback[i] = FEEDBACK_OPTIONS[next_index]
                        st.rerun() # Rerun to update the button color below

                    # Display colored square below button to show current selection
                    color = get_color(current_status)
                    st.markdown(f'<div style="width:30px; height:10px; background-color:{color}; margin: auto; border: 1px solid black;"></div>', unsafe_allow_html=True)


            # --- Submit Button ---
            if st.button("Submit Guess and Feedback"):
                # Validation
                if len(guess) != WORD_LENGTH or not guess.isalpha():
                    st.warning("Please enter a valid 5-letter word.")
                elif guess not in solver.all_words:
                    st.warning(f"'{guess.upper()}' is not in the valid word list.")
                else:
                    # Process the guess
                    feedback_str = "".join(st.session_state.current_feedback)

                    # Update Solver State
                    solver.feedback_history.append((guess, feedback_str))
                    solver.guesses_made += 1

                    # Update Streamlit State
                    st.session_state.solver_history.append((guess, feedback_str))
                    st.session_state.display_history.append((guess, list(st.session_state.current_feedback))) # Store list for display
                    st.session_state.guesses_made += 1

                    # Check for win/loss
                    if feedback_str == CORRECT * WORD_LENGTH:
                        st.session_state.solved = True
                        st.session_state.game_over = True
                    elif st.session_state.guesses_made >= MAX_GUESSES:
                        st.session_state.game_over = True

                    # Reset for next guess
                    st.session_state.current_feedback = list(DEFAULT_FEEDBACK)
                    st.session_state.current_guess_input = "" # Clear input for next suggestion


                    # Trigger filter and rerun
                    solver.filter_words() # Update possible answers in the solver
                    st.rerun()
        elif guess: # If guess is partially typed or invalid
            st.warning("Type a 5-letter word to enable feedback input.")

# Optional: Display remaining words if few are left
if not st.session_state.game_over and len(solver.possible_answers) <= 15 and len(solver.possible_answers) > 1 :
    with grid_col: # Put this below the grid
        st.write("---")
        st.write("**Potential Answers:**")
        st.write(", ".join(sorted(list(solver.possible_answers))))
