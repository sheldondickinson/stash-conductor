"""Local human given names. Automatic allocation runs inside the creation transaction."""

import secrets

from .models import Container

# Curated English given names, including established names adopted into English.
# This is application data, with no network or generative service dependency.
NAMES = tuple(
    """
Adam Adrian Albert Alec Alexander Alfred Alistair Andrew Anthony Archie Arnold Arthur
Ashley Austin Barnaby Barry Basil Benedict Benjamin Bernard Bertie Billy Blake Bradley
Brandon Brian Bruce Bryan Caleb Calvin Cameron Carl Cecil Cedric Charles Chester Chris
Christopher Clarence Clive Colin Conrad Craig Cyril Daniel David Dean Dennis Derek
Dominic Donald Douglas Duncan Edgar Edmund Edward Edwin Eli Elias Elliot Ellis Eric
Ernest Ethan Eugene Evan Felix Finlay Francis Frank Frederick Gareth Gavin Geoffrey
George Gerald Gilbert Giles Gordon Graham Gregory Harold Harry Harvey Henry Herbert
Horace Howard Hugh Hugo Ian Isaac Jack Jacob James Jasper Jeremy Jerome Jesse Joel
John Jonathan Joseph Joshua Julian Justin Keith Kenneth Kevin Laurence Lawrence Lee
Leon Leonard Leslie Lewis Liam Lionel Lloyd Logan Louis Lucas Malcolm Marcus Mark
Martin Matthew Maurice Max Michael Miles Milton Morgan Nathan Nathaniel Neil Nicholas
Nigel Noah Noel Norman Oliver Oscar Oswald Owen Patrick Paul Percy Peter Philip
Phillip Quentin Ralph Raymond Reginald Reuben Richard Robert Robin Roger Roland Ronald
Roy Rupert Russell Ryan Samuel Scott Sebastian Seth Sidney Simon Stanley Stephen
Steven Stuart Sydney Terence Theodore Thomas Timothy Tobias Toby Trevor Tristan
Vernon Victor Vincent Walter Warren Wayne Wesley Wilfred Will William Winston Zachary
Abigail Ada Adelaide Adele Agnes Alexandra Alice Alison Amanda Amelia Amy Angela
Ann Anna Anne Annabel Annette Audrey Barbara Beatrice Belinda Beryl Beth Bethany
Betty Beverley Bonnie Brenda Bridget Camilla Carol Caroline Catherine Cecilia Celia
Charlotte Cheryl Chloe Christine Claire Clara Clarice Claudia Connie Constance Cora
Cynthia Daisy Daphne Deborah Delia Denise Diana Diane Dora Doris Dorothy Edith
Edna Elaine Eleanor Elena Eliza Elizabeth Ella Ellen Elsie Emily Emma Enid Erica
Erin Esme Esther Ethel Eva Evelyn Faith Felicity Fiona Flora Florence Frances Freya
Gabrielle Gail Gemma Georgia Georgina Geraldine Gillian Gladys Gloria Grace Greta
Gwendoline Gwen Hannah Harriet Hazel Heather Helen Henrietta Hilda Holly Hope Imogen
Irene Iris Isabel Isabella Isla Ivy Jacqueline Jane Janet Janice Jean Jemima Jennifer
Jessica Jill Joan Joanna Jocelyn Josephine Joy Joyce Judith Julia Julie June Karen
Kate Katherine Kathleen Katie Kay Laura Lauren Lavinia Leah Leona Lesley Lillian
Lily Linda Lindsey Lisa Lois Lorraine Louisa Louise Lucy Lydia Mabel Madeleine
Madeline Mae Maggie Maisie Margaret Margot Maria Marian Marion Marjorie Martha Mary
Matilda Maud Maureen Mavis May Megan Melanie Melissa Meredith Mildred Millie Miranda
Miriam Molly Monica Nancy Naomi Natalie Nell Nellie Nicola Nina Nora Olive Olivia
Pamela Patricia Pauline Pearl Peggy Penelope Philippa Phoebe Phyllis Polly Poppy
Priscilla Prudence Rachel Rebecca Renee Rita Roberta Rosalind Rosemary Rose Ruby
Ruth Sally Samantha Sandra Sara Sarah Selena Serena Sharon Sheila Shirley Simone
Sophie Sophia Stella Stephanie Sue Susan Suzanne Sylvia Tabitha Teresa Thelma
Theresa Tilly Una Valerie Vanessa Vera Veronica Victoria Violet Vivienne Wendy
Winnie Winifred Yvonne Zoe
""".split()
)


def normalise(value):
    return value.strip().casefold()


class NameAllocator:
    def __init__(self, extra=()):
        self.used = {
            normalise(n) for n in Container.objects.values_list("name", flat=True)
        }
        self.used.update(normalise(n) for n in extra)
        self.pool = list(NAMES)
        secrets.SystemRandom().shuffle(self.pool)
        self.bases = set(NAMES)

    def allocate(self, preferred=""):
        # A proposed automatic name may have become unavailable since preview.
        base, _, suffix = preferred.rpartition(" ")
        allowed = preferred in self.bases or (
            base in self.bases and suffix.isdigit() and 2 <= int(suffix) <= 10**9
        )
        if allowed and normalise(preferred) not in self.used:
            name = preferred
        else:
            while self.pool and normalise(self.pool[-1]) in self.used:
                self.pool.pop()
            if self.pool:
                name = self.pool.pop()
            else:
                base = secrets.choice(NAMES)
                prefix = normalise(base) + " "
                suffixes = [
                    int(n[len(prefix) :])
                    for n in self.used
                    if n.startswith(prefix) and n[len(prefix) :].isdigit()
                ]
                name = f"{base} {max([1, *suffixes]) + 1}"
        self.used.add(normalise(name))
        return name
