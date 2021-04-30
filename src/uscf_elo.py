import numpy as np
from datetime import date
from collections import Counter

'''
This package is an implementation of the US Chess Federation (USCF) rating system for Over-The-Board (OTB) events. Details can be found here: http://www.glicko.net/ratings/rating.system.pdf
'''


class Player:

    def __init__(self, rating, nr_games_played, nr_wins, nr_losses, birth_date=date(1990, 1, 1), tournament_end_date=date(2021, 1, 1), Nr=0):
        self.nr_games_played = nr_games_played
        self.nr_wins = nr_wins
        self.nr_losses = nr_losses
        self.rating = rating
        self.birth_date = birth_date
        self.tournament_end_date = tournament_end_date
        self.Nr = Nr
        self.initial_rating = self.initialize_rating()
        self.established_rating = self.determine_established_rating()
        self.effective_nr_games = self.compute_effective_nr_games()
        self.rating_type = self.compute_rating_type()

    def determine_established_rating(self):
        if self.nr_games_played > 25:
            established_rating = True
        else:
            established_rating = False
        return established_rating

    def compute_age_based_rating(self):
        age = (self.tournament_end_date - self.birth_date).days/365.25
        if age < 2:
            rating = 100
        elif 2 <= age <= 26:
            rating = 50*age
        else:
            rating = 1300
        return rating

    def initialize_rating(self):
        if self.rating is None:
            initial_rating = self.compute_age_based_rating()
        else:
            initial_rating = self.rating
        return initial_rating

    def compute_effective_nr_games(self):
        if self.initial_rating <= 2355:
            n = 50/np.sqrt(0.662 + 0.00000739*(2569 -
                           self.initial_rating)**2)
        else:
            n = 50

        effective_nr_games = min(n, self.nr_games_played)
        return effective_nr_games

    def compute_rating_type(self):
        if self.nr_games_played <= 8:
            rating_type = 'special-new'
        elif self.nr_wins == self.nr_games_played:
            rating_type = 'special-only-wins'
        elif self.nr_losses == self.nr_games_played:
            rating_type = 'special-only-losses'
        else:
            rating_type = 'standard'
        return rating_type

    def create_tournament(self, tournament_results):
        return self.Tournament(self, tournament_results)

    class Tournament:

        epsilon_special_rating = 10**-7
        absolute_rating_floor = 100
        B = 14

        # Note: tournament_results needs to be in a specific format: a list of tuples/lists, each representing one match and containing (opponent_id, opponent_rating, score), where score is 1 for a win, 0.5 for a draw and 0 for a loss

        def __init__(self, player, tournament_results, time_control_minutes=60, time_control_increment_seconds=0):
            self.player = player
            self.nr_games_tournament = len(tournament_results)
            self.tournament_score = sum([i[2] for i in tournament_results])
            self.tournament_results = tournament_results
            self.time_control_minutes = time_control_minutes
            self.time_control_increment_seconds = time_control_increment_seconds
            self.adjusted_initial_rating, self.adjusted_score = self.compute_adjusted_initial_rating_and_score()

        def compute_pwe(self, player_rating, opponent_rating):
            if player_rating <= opponent_rating - 400:
                pwe = 0
            elif opponent_rating - 400 < player_rating < opponent_rating + 400:
                pwe = 0.5 + (player_rating - opponent_rating)/800
            else:
                pwe = 1

            return pwe

        # players with <= 8 games, or players that have had only wins/losses in all previous rated games, get a special rating
        def compute_adjusted_initial_rating_and_score(self):

            # tournament results must be structured as a list of tuples (rating, opponent_rating, result)

            if self.player.rating_type == 'special-only-wins':
                adjusted_initial_rating = self.player.initial_rating - 400
                adjusted_score = self.tournament_score + self.player.effective_nr_games
            elif self.player.rating_type == 'special-only-losses':
                adjusted_initial_rating = self.player.initial_rating + 400
                adjusted_score = self.tournament_score
            else:
                adjusted_initial_rating = self.player.initial_rating
                adjusted_score = self.tournament_score + self.player.effective_nr_games/2

            return adjusted_initial_rating, adjusted_score

        def special_rating_objective(self, special_rating_estimate):

            # tournament results must be structured as a list of tuples (rating, opponent_rating, result)
            sum_pwe = sum([self.compute_pwe(special_rating_estimate, t[1])
                          for t in self.tournament_results])

            objective_fn = self.player.effective_nr_games * \
                self.compute_pwe(special_rating_estimate, self.adjusted_initial_rating) + \
                sum_pwe - self.adjusted_score

            return objective_fn

        def special_rating_step_2(self, M, f_M, Sz):
            step_2_satisfied = False
            while step_2_satisfied is False:

                # Let za be the largest value in Sz for which M > za.
                za = max([z for z in Sz if z < M])
                f_za = self.special_rating_objective(za)

                print(za, f_za)

                if abs(f_M - f_za) < self.epsilon_special_rating:
                    M = za
                    f_M = f_za
                    print('if 1,', M, f_M)
                    continue
                else:
                    M_star = M - f_M * ((M - za) / (f_M - f_za))
                    print('M_star', M_star)
                    if M_star < za:
                        M = za
                        f_M = f_za
                        print('step 2', M, f_M)
                        continue
                    elif za <= M_star < M:
                        M = M_star
                        f_M = self.special_rating_objective(M_star)
                        print('step 3', M, f_M)
                        continue
                    else:
                        step_2_satisfied = True
                        print('final', M, f_M)
                        break
            return M, f_M

        def special_rating_step_3(self, M, f_M, Sz):
            step_3_satisfied = False
            while step_3_satisfied is False:

                zb = min([z for z in Sz if z > M])
                f_zb = self.special_rating_objective(zb)
                if abs(f_zb - f_M) < self.epsilon_special_rating:
                    M = zb
                    f_M = f_zb
                else:
                    M_star = M - f_M * ((zb - M) / (f_zb - f_M))
                    if M_star > zb:
                        M = zb
                        f_M = self.special_rating_objective(M)
                        continue
                    elif M < M_star <= zb:
                        M = M_star
                        f_M = self.special_rating_objective(M)
                        continue
                    else:
                        step_3_satisfied = True
                        return M, f_M

        def special_rating_step_4(self, f_M, opponent_ratings, M, Sz):
            p = 0
            if abs(f_M) < self.epsilon_special_rating:
                p = len([o for o in opponent_ratings if abs(M - o) <= 400])
            if abs(M - self.adjusted_initial_rating) <= 400:
                p += 1
            if p > 0:
                pass
            elif p == 0:
                za = max([s for s in Sz if s < M])
                zb = min([s for s in Sz if s > M])
                if za <= self.player.initial_rating <= zb:
                    M = self.player.initial_rating
                elif self.player.initial_rating < za:
                    M = za
                elif self.player.initial_rating > zb:
                    M = zb
                else:
                    raise Exception(
                        'M is outside the range of expected values.')

            M = min(2700, M)
            return M

        def compute_M(self, effective_nr_games, initial_rating, opponent_ratings, tournament_score, tournament_games):
            M = (effective_nr_games*initial_rating + sum(opponent_ratings) + 400 *
                 (2*tournament_score - tournament_games))/(effective_nr_games + tournament_games)
            return M

        def compute_Sz(self, opponent_ratings):
            Sz = [o + 400 for o in opponent_ratings] + \
                [o - 400 for o in opponent_ratings]
            return Sz

        def compute_special_rating(self):

            tournament_games = len(self.tournament_results)
            tournament_score = sum([t[2] for t in self.tournament_results])
            opponent_ratings = [r[1] for r in self.tournament_results]

            M = self.compute_M(self.player.effective_nr_games, self.player.initial_rating,
                               opponent_ratings, tournament_score, tournament_games)

            f_M = self.special_rating_objective(M)
            Sz = self.compute_Sz(opponent_ratings)

            if f_M > self.epsilon_special_rating:
                M, f_M = self.special_rating_step_2(M, f_M, Sz)

            if f_M < -self.epsilon_special_rating:
                M, f_M = self.special_rating_step_3(M, f_M, Sz)

            if abs(f_M) < self.epsilon_special_rating:
                M = self.special_rating_step_4(f_M, opponent_ratings, M, Sz)
                M = min(2700, M)
                return M

        def compute_standard_rating_K(self, rating, time_control_minutes, time_control_increment_seconds, effective_nr_games, nr_games_tournament):

            K = 800/(effective_nr_games + nr_games_tournament)

            if 30 <= (time_control_minutes + time_control_increment_seconds) <= 65 and rating > 2200:
                if rating < 2500:
                    K = (800 * (6.5 - 0.0025*rating))/(effective_nr_games +
                                                       nr_games_tournament)
                else:
                    K = 200/(effective_nr_games +
                             nr_games_tournament)
            return K

        def compute_standard_winning_expectancy(self, rating, opponent_rating):
            winning_expectancy = 1/(1+10**-((rating - opponent_rating)/400))
            return winning_expectancy

        def compute_standard_rating(self):
            sum_swe = sum([self.compute_standard_winning_expectancy(
                self.player.initial_rating, r[1]) for r in self.tournament_results])

            K = self.compute_standard_rating_K(
                self.player.initial_rating, self.time_control_minutes, self.time_control_increment_seconds, self.player.effective_nr_games, self.nr_games_tournament)

            opponent_ids = [i[0] for i in self.tournament_results]
            max_nr_games_one_opponent = max(Counter(opponent_ids).values())

            if self.nr_games_tournament < 3 or max_nr_games_one_opponent > 2:

                rating_new = self.player.initial_rating + \
                    K*(self.tournament_score - sum_swe)
            else:

                rating_new = self.player.initial_rating + K*(self.tournament_score - sum_swe) + max(
                    0, K*(self.tournament_score - sum_swe) - self.B*np.sqrt(max(self.nr_games_tournament, 4)))

            return rating_new

        # after the tournament has been played, the rating cannot be lower than the rating floor. this function disregards OTB rating floor considerations for people with an original Life Master Title, or those people that win a large cash prize
        def compute_rating_floor(self):

            # number of total wins after the tournament
            Nw = self.player.nr_wins + \
                len([i for i in self.tournament_results[2] if i == 1])

            # number of total draws after the tournament
            Nd = self.player.nr_games_played - self.player.nr_wins - self.player.nr_losses + \
                len([i for i in self.tournament_results[2] if i == 0.5])

            # number of events in which a player has completed three rating games. defaults to 0 when class initialized, but other value can be specified
            if len(self.tournament_results) >= 3:
                self.player.Nr += 1

            otb_absolute_rating_floor = min(
                self.absolute_rating_floor + 4*Nw + 2*Nd + self.player.Nr, 150)

            # a player with an established rating has a rating floor possibly higher than the absolute floor. Higher rating floors exists at 1200 - 2100
            if self.player.initial_rating >= 1200 and self.player.established_rating is True:
                otb_absolute_rating_floor = int(
                    (self.player.initial_rating - 200) / 100)*100

            return otb_absolute_rating_floor

        def update_rating(self):

            if self.player.rating_type == 'standard':
                updated_rating = self.compute_standard_rating()
            else:
                updated_rating = self.compute_special_rating()

            # individual matches are rated if both players have an established published rating, with the difference in ratings not to exceed 400 points
            # note: this does not capture logic specifying that the max net rating change in 180 days due to match play is 100 points, and that the max net rating change in 3 years due to match play is 200 points
            if self.nr_games_tournament == 1 and abs(self.player.initial_rating - self.tournament_results[0][1]) > 400:
                updated_rating_bounded = self.player.initial_rating
            else:
                if self.nr_games_tournament == 1 and abs(self.player.initial_rating - self.tournament_results[0][1]) <= 400:
                    updated_rating_bounded = min(max(
                        self.player.initial_rating - 50, updated_rating), self.player.initial_rating + 50, updated_rating)
                else:
                    updated_rating_bounded = max(
                        updated_rating, self.compute_rating_floor())

                # now update the player's overall number of games played, wins, losses
                self.player.nr_games_played += len(self.tournament_results)
                self.player.nr_wins += len(
                    [t for t in self.tournament_results if t[2] == 1])
                self.player.nr_losses += len(
                    [t for t in self.tournament_results if t[2] == 0])

            return updated_rating_bounded
