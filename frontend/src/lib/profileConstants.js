// Interest catalogue for Lovreski profile picker — 8 categories with emojis.
export const INTEREST_CATEGORIES = [
  { key: "romance", label: "Romance & Passion", emoji: "💕", items: [
    "Kisses", "Hugs", "Flirt", "Romantic dinners", "Compliments", "Massage", "Touching",
    "Watch romantic movies", "Underwear", "Deep conversations", "Dramas", "Spontaneous surprises",
    "Video Games", "Fashion and Beauty", "Cars", "IT and Tech", "Psychology", "Meditation",
    "Language Learning", "Dancing", "Make Love", "Fan Fiction",
  ]},
  { key: "social", label: "Social Life", emoji: "🎉", items: [
    "Travel", "Shopping", "Camping", "Museums and Galleries", "Partying and Clubbing",
    "Meeting with Friends", "Active Recreation", "Karaoke", "Art",
  ]},
  { key: "creative", label: "Quizzes & Creativity", emoji: "🎨", items: [
    "Photography", "Music", "Design", "Makeup", "Blogging", "Painting",
  ]},
  { key: "active", label: "Active Lifestyle", emoji: "🏃", items: [
    "Running", "Yoga", "Fitness", "Walks", "Mountain Climbing", "Swimming", "Horseback Riding",
  ]},
  { key: "food", label: "Food & Drinks", emoji: "🍕", items: [
    "Healthy Eating", "Coffee and Tea", "Drink with Friends", "Spicy Food",
  ]},
  { key: "sports", label: "Sports", emoji: "⚽", items: [
    "Football", "Basketball", "Hockey", "Swimming",
  ]},
  { key: "home", label: "Home Time", emoji: "🏠", items: [
    "Cooking", "Board Games", "Books",
  ]},
  { key: "personal", label: "Personal Development", emoji: "📚", items: [
    "Online Learning", "Travel", "Cartoons",
  ]},
];

export const GOAL_OPTIONS = [
  { value: "long_term", emoji: "💑", label: "Long-term commitment" },
  { value: "chat", emoji: "💬", label: "To chat and meet new people" },
  { value: "friendship", emoji: "👫", label: "Friendship" },
  { value: "experience", emoji: "✨", label: "New Experience" },
];

export const RELATIONSHIP_OPTIONS = ["Single", "Multiple", "Complicated", "Taken", "Not to answer"];
export const KIDS_OPTIONS = ["No kids", "I have kids", "No answer"];
export const SMOKING_OPTIONS = ["Don't smoke", "Rarely", "Smoke", "Not to answer"];
export const ALCOHOL_OPTIONS = ["Don't drink", "Rarely", "Drink", "Not to answer"];
export const GENDER_OPTIONS = [
  { value: "male", label: "Мужской" },
  { value: "female", label: "Женский" },
  { value: "non_binary", label: "Небинарный" },
  { value: "prefer_not", label: "Не указывать" },
];
