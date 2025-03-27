import re
import string
from collections import Counter, defaultdict
from typing import List, Tuple

class WordleSolver:
    def __init__(self, wordlist_path: str, answers_path: str = None):
        self.all_words = self.load_words(wordlist_path)
        self.possible_answers = self.load_words(answers_path) if answers_path else self.all_words.copy()
        self.guesses_made = 0
        self.feedback_history = []  # Store guess and feedback tuples
        self.known_letters = ['' for _ in range(5)]  # Green letters
        self.misplaced_letters = [set() for _ in range(5)] # Yellow letters, per position
        self.excluded_letters = set() # Gray letters

    def load_words(self, filepath: str) -> set[str]:
        """Loads words from a file, ensuring they are valid."""
        with open(filepath, 'r') as f:
            words = {word.strip().lower() for word in f if len(word.strip()) == 5 and word.strip().isalpha()}
        return words

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

    def score_word(self, word: str, positional_frequencies: list[Counter], letter_frequencies: Counter, elimination_mode: bool = False) -> float:
        """Scores a word based on frequencies and elimination potential."""
        score = 0.0
        used_letters = set()

        for i, letter in enumerate(word):
            if letter not in used_letters:
                score += positional_frequencies[i][letter]
                if elimination_mode:
                  score += letter_frequencies[letter]  # Add elimination bonus
                used_letters.add(letter)

        return score

    def filter_words(self) -> set[str]:
      """Filters the possible words based on accumulated feedback."""
      filtered_words = self.possible_answers.copy()

      for guess, feedback in self.feedback_history:
          for i, (letter, status) in enumerate(zip(guess, feedback)):
              if status == 'G':
                  # Keep only words with the correct letter in this position
                  filtered_words = {word for word in filtered_words if word[i] == letter}
                  self.known_letters[i] = letter
              elif status == 'Y':
                  # Keep words containing the letter, but not in this position
                  filtered_words = {word for word in filtered_words if letter in word and word[i] != letter}
                  self.misplaced_letters[i].add(letter)
              elif status == 'X':
                  # Keep words NOT containing the letter, UNLESS it's a green/yellow elsewhere
                  if letter not in [l for l in self.known_letters if l] and letter not in set().union(*self.misplaced_letters):
                    filtered_words = {word for word in filtered_words if letter not in word}
                    self.excluded_letters.add(letter)

      return filtered_words

    def suggest_guess(self, words: set[str], elimination_mode: bool = False) -> str:
        """Suggests the best guess based on scoring."""
        if not words:
            return "No valid words remaining."

        positional_frequencies = self.calculate_positional_frequencies(words)
        letter_frequencies = self.calculate_letter_frequencies(words) # For elimination

        best_word = ""
        best_score = -1

        for word in (self.all_words if elimination_mode else words):
            score = self.score_word(word, positional_frequencies, letter_frequencies, elimination_mode)
            if score > best_score:
                best_score = score
                best_word = word

        return best_word

    def get_user_feedback(self, guess: str) -> str:
        """Gets and validates feedback from the user."""
        while True:
            feedback = input(f"Enter feedback for '{guess}' (G=Green, Y=Yellow, X=Gray): ").upper()
            if len(feedback) == 5 and all(c in 'GYX' for c in feedback):
                return feedback
            print("Invalid feedback format. Please use 5 characters (G, Y, or X).")

    def solve(self):
        """Main solver loop."""
        print("Wordle Solver")
        elimination_turns = 2 # Use elimination mode for the first 2 turns.

        while self.guesses_made < 6:
            self.guesses_made += 1
            remaining_words = self.filter_words()
            print(f"\nPossible words remaining: {len(remaining_words)}")
            if len(remaining_words) <= 20: # Show options if few remain
              print(f"Possible words: {', '.join(sorted(remaining_words))}")

            elimination_mode = self.guesses_made <= elimination_turns and len(remaining_words) > 2
            suggested_guess = self.suggest_guess(remaining_words, elimination_mode)

            print(f"Suggested guess: {suggested_guess}")
            if len(remaining_words) == 1:
                print(f"The answer is: {suggested_guess}")
                return

            user_guess = input("Enter your guess (or press Enter to use suggested guess): ").lower()
            guess = user_guess if user_guess else suggested_guess

            if guess not in self.all_words:
                print("Invalid guess.  Please choose a valid 5-letter word.")
                self.guesses_made -= 1  # Don't count invalid guesses
                continue

            feedback = self.get_user_feedback(guess)
            self.feedback_history.append((guess, feedback))

            if feedback == 'GGGGG':
                print(f"Solved in {self.guesses_made} guesses!")
                return

        print("Failed to solve within 6 guesses.")

# Example usage (assuming you have wordlist.txt and answers.txt):
if __name__ == "__main__":
    solver = WordleSolver("wordlist.txt", "answers.txt")
    solver.solve()
